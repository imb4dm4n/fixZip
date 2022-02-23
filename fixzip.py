'''
修复 zip 的工具模块
'''
import io
import struct

structEndArchive = b"<4s4H2LH"
stringEndArchive = b"PK\005\006"
sizeEndCentDir = struct.calcsize(structEndArchive)

structCentralDir = "<4s4B4HL2L5H2L"
stringCentralDir = b"PK\001\002"
sizeCentralDir = struct.calcsize(structCentralDir)

structFileHeader = "<4s2B4HL2L2H"
stringFileHeader = b"PK\003\004"
sizeFileHeader = struct.calcsize(structFileHeader)
_FH_SIGNATURE = 0
_FH_EXTRACT_VERSION = 1
_FH_EXTRACT_SYSTEM = 2
_FH_GENERAL_PURPOSE_FLAG_BITS = 3
_FH_COMPRESSION_METHOD = 4
_FH_LAST_MOD_TIME = 5
_FH_LAST_MOD_DATE = 6
_FH_CRC = 7
_FH_COMPRESSED_SIZE = 8
_FH_UNCOMPRESSED_SIZE = 9
_FH_FILENAME_LENGTH = 10
_FH_EXTRA_FIELD_LENGTH = 11


structFileRecord = "<4s5H3I2H"
sizeFileRecord = struct.calcsize(structFileRecord)

structDirEntry = "<4s6H3I5H2I"
sizestructDirEntry =  struct.calcsize(structDirEntry)
print("sizeFileRecord = {} sizeFileHeader = {}".format(sizeFileRecord, sizeFileHeader))
# print("sizeCentralDir = {} sizestructDirEntry = {}".format(sizeCentralDir, sizestructDirEntry))

# 描述部分
structDataDescp = "<4s3L"
sizeDataDescp = struct.calcsize(structDataDescp)
stringDataDescp = b"PK\x07\x08"


def fix_zip_lost_of_ced(raw_data):
    '''
    1. 修复丢失的 end of central directory 
    '''

    fpin = io.BytesIO(raw_data)
    # Determine file size
    fpin.seek(0, 2)
    filesize = fpin.tell()
    print("[+]original size ".format(filesize))

    # Check to see if this is ZIP file with no archive comment (the
    # "end of central directory" structure should be the last item in the
    # file if this is the case).
    try:
        fpin.seek(-sizeEndCentDir, 2)
    except OSError:
        return None
    data = fpin.read()
    if (len(data) == sizeEndCentDir and
        data[0:4] == stringEndArchive and
        data[-2:] == b"\000\000"):
        # 魔术字正常，直接返回
        return raw_data

    # 回退 64 kb 内存，搜索魔术字
    maxCommentStart = max(filesize - (1 << 16) - sizeEndCentDir, 0)
    fpin.seek(maxCommentStart, 0)
    data = fpin.read()
    start = data.rfind(stringEndArchive)
    # 不需要修复
    if start >= 0:
        return raw_data
    else:
        # 开始修复 zip
        cur_offset = 0
        li_cd = []  # central directory
        li_name_ext = []    # 存储所有文件名和ext
        name_field_len = 0
        num_file_record = 0
        while cur_offset < filesize:
            # 顺序解析 file record 直到结束
            fpin.seek(cur_offset, 0)
            data = fpin.read(sizeFileHeader)
            try:
                file_record = struct.unpack(structFileHeader, data)
                if file_record[_FH_SIGNATURE] != stringFileHeader:
                    # print("[!]not file record signature! exit! {}".format(file_record[0]))
                    raise Exception("[!]not file record signature! exit! {}".format(file_record[0]))
                # 输出文件名、crc32、解压后大小
                num_file_record += 1
                fname = fpin.read(file_record[_FH_FILENAME_LENGTH])
                ext_field = fpin.read(file_record[_FH_EXTRA_FIELD_LENGTH])
                crc = file_record[_FH_CRC]
                size_uncompress = file_record[_FH_UNCOMPRESSED_SIZE]
                size_compress = file_record[_FH_COMPRESSED_SIZE]
                ext_len = file_record[_FH_EXTRA_FIELD_LENGTH]
                name_field_len += file_record[_FH_FILENAME_LENGTH]+ ext_len

                
                # print("file name {} crc32 = {} uncompress size = {}".format(fname, crc, size_uncompress))

                central_dir = struct.pack(structCentralDir,stringCentralDir,\
                    20,\
                    0,
                    20,\
                    0,
                    file_record[_FH_GENERAL_PURPOSE_FLAG_BITS],\
                    file_record[_FH_COMPRESSION_METHOD],\
                    file_record[_FH_LAST_MOD_TIME],\
                    file_record[_FH_LAST_MOD_DATE],\
                    file_record[_FH_CRC],\
                    file_record[_FH_COMPRESSED_SIZE],\
                    file_record[_FH_UNCOMPRESSED_SIZE],\
                    file_record[_FH_FILENAME_LENGTH],\
                    # 0,\
                    file_record[_FH_EXTRA_FIELD_LENGTH],\
                    # 0,\
                    0,
                    0,
                    0,
                    0,
                    cur_offset,
                    )
                
                li_cd.append(central_dir)
                li_name_ext.append((fname, ext_field))

                # 移动指针到末尾，写入新数据
                # fpin.seek(0, 2)
                # # 输出一个 central directory
                # fpin.write(central_dir)
                # # 写入文件名和ext field
                # fpin.write(fname)
                # fpin.write(ext_field)
                
                cur_offset += file_record[_FH_FILENAME_LENGTH] + ext_len + sizeFileHeader + size_compress

            
            except Exception as  e:
                # print("[+]{}".format(e))
                # print("[+]current offset {}".format(cur_offset))
                try:
                    fpin.seek(cur_offset, 0)
                    data = fpin.read(sizeDataDescp)
                    descp = struct.unpack(structDataDescp, data)

                    if descp[0] != stringDataDescp:
                        # print("[+]not data descp {} != {}".format(descp[0], stringDataDescp))
                        break
                    cur_offset += sizeDataDescp
                    # print("[+]has data descp")
                    continue
                except Exception as e:
                    # print("[+]another error {}".format(e))
                    break

        fpin.seek(cur_offset, 0)
        offset_cd = cur_offset
        for i in range(0,len(li_cd)):
            cd = li_cd[i]
            nt = li_name_ext[i]
            fpin.write(cd)
            fpin.write(nt[0])
            fpin.write(nt[1])
            cur_offset += len(cd) + len(nt[0]) + len(nt[1])

        # 严格的拼接到 cd 后面，否则解析zip时会认为有额外文件
        fpin.seek(cur_offset, 0)
        # print("[+]we have {} of file records ".format(num_file_record))
        # 构造 end of central directory 4s  4H 2L  H, 写入到文件结尾
        end_cd = struct.pack(structEndArchive, stringEndArchive,
            0,
            0,
            len(li_cd),
            len(li_cd),
            len(li_cd) * sizeCentralDir + name_field_len,   # central dir 大小
            offset_cd,   # central dir 的偏移
            0
            )
        
        fpin.write(end_cd)
        # print("[+]apk is now fixed ! ")
        fpin.seek(0, 2)
        sz = fpin.tell()
        fpin.seek(0, 0)
        # print("[+]new file size {} ".format(sz))
        return fpin.read(sz)


# file_path = "D:\\work\\apkZipStudy\\bad_end_of_dir\\error4.apk"
# fp = open(file_path, "rb")
# data = fp.read()


# with open("fixzip.apk", "wb") as f:
#     fix = fix_zip_lost_of_ced(data)
#     f.write(fix)
#     print("[+]fix zip write to fixzip.apk")
