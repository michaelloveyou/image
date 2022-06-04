#! /usr/bin/python3

import json
import re
import os
import struct

s_section_key_list = ["partition", "firmware", "start_addr", "size"]
s_base_addr = 0
SZ_16M = 0x1000000

# Physical address to virtual address
def p2v(addr):
    return (addr - s_base_addr)

def hex2int(str):
    return int(str, base=16) % (2**32)

def decimal2int(str):
    return int(str, base=10) % (2**32)

def crc_size(size):
    return ((size >> 5) * 34)

def crc_addr(addr):
    return crc_size(addr)

def size2int(str):
    size_str = re.findall(r"\d+", str)
    size = decimal2int(size_str[0])

    unit = re.findall(r"[k|K|m|M|g|G]+", str)
    if (unit[0] == 'k') or (unit[0] == 'K'):
        return size * (1<<10)
    elif (unit[0] == 'm') or (unit[0] == 'M'):
        return size * (1<<20)
    elif (unit[0] == 'g') or (unit[0] == 'G'):
        return size * (1<<30)
    else:
        print(f'invalid size unit {unit[0]}, must be "k/K/m/M/g/G"')

def is_out_of_range(addr, size):
    if ( (addr + size) >= SZ_16M):
        return True
    return False

class image:
    def check_field(self):
        for k in s_section_key_list:
            if k not in self.img_json.keys():
                print(f'Following image does not contain field "{k}":')
                print(self.image_json)
                exit(0)

    def __init__(self, idx, img_dic):
        global s_base_addr
        self.idx = idx
        self.img_json = img_dic

        self.check_field()

        self.firmware = img_dic['firmware']

        if not os.path.exists(self.firmware):
            print(f'image{idx} firmware %s not exists' %(self.firmware))
            exit(0)

        self.firmware_size = os.path.getsize(self.firmware)
        self.crc_firmware_size = crc_size(self.firmware_size)

        self.partition = img_dic['partition']

        self.cpu_start_addr = hex2int(img_dic['start_addr'])
        self.cpu_size = size2int(img_dic['size'])

        # Must init s_base_addr before checking address!
        if (idx == 0):
            s_base_addr = self.cpu_start_addr
            self.cpu_start_addr = 0
        else:
            if (self.cpu_start_addr <= s_base_addr):
                print(f'image{self.idx} start_addr=%x < base_addr=%x' %(self.cpu_start_addr, s_base_addr))
                exit(0)
            self.cpu_start_addr = p2v(self.cpu_start_addr)

        if is_out_of_range(self.cpu_start_addr, self.cpu_size):
            print(f'image{self.idx} start=%x size=%x is out of range' %(self.cpu_start_addr, self.cpu_size))
            exit(0)

        if ((self.cpu_start_addr % 32) != 0):
            print(f'image%x start_addr=%x is not 32 bytes aligned' %(self.cpu_start_addr))
            exit(0)

        if (self.firmware_size > self.cpu_size):
            print(f'image{idx} firmware size %x > %x' %(self.firmware_size, self.cpu_size))
        self.crc_start_addr = self.cpu_start_addr
        self.crc_size = self.cpu_size
        self.crc_en = False
        self.enc_start_addr = self.cpu_start_addr
        self.enc_size = self.cpu_size
        self.enc_en = False

        if ("crc" in img_dic):
            if (img_dic['crc'] == 'y') or (img_dic['crc'] == 'Y'):
                self.crc_start_addr = crc_addr(self.cpu_start_addr)
                self.crc_size = crc_size(self.cpu_size)
                self.crc_en = True

        if is_out_of_range(self.crc_start_addr, self.crc_size):
            print(f'image{self.idx} crc is out of range')
            exit(0)

        print(f'image%x cpu_start=%x size=%x, crc_start=%x, size=%x, enc_start=%x enc_end=%x'
                %(self.idx, self.cpu_start_addr, self.cpu_size, self.crc_start_addr, self.crc_size, self.enc_start_addr, self.enc_size))

    def add_crc(self):
        self.raw_buf = bytearray(self.firmware_size)
        self.crc_buf = bytearray(self.crc_firmware_size)
        print(f'===========> firmware={self.firmware}')
        with open(self.firmware, 'rb') as f:
            #f.readinto(self.raw_buf) TODO add CRC16
            self.crc_buf =  f.read()
            print(self.crc_buf)
       
class images:

    def __init__(self, json_file_name, output_file_name):
        self.imgs = []
        self.output_file_name = output_file_name
        self.json_file_name = json_file_name
        if not os.path.exists(json_file_name):
            print(f'JSON configuration file {json_file_name} not exists')
            exit(0)

        with open(json_file_name, 'r') as self.json_file:
            self.json_data = json.load(self.json_file)
        self.check_json_data()

    def check_json_data(self):
        if ("images" not in self.json_data):
            print('json does not contain field "images"!')
            exit(0)

        self.imgs_cnt = len(self.json_data['images'])
        if (self.imgs_cnt == 0):
                print(f'images of json does not contain any item!')
                exit(0)

        for idx in range(self.imgs_cnt):
            img = image(idx, self.json_data['images'][idx])
            self.imgs.append(img)

        for idx in range(self.imgs_cnt):
            if (idx == 0):
                continue

            pre_crc_start_addr = self.imgs[idx - 1].crc_start_addr
            pre_crc_size = self.imgs[idx - 1].crc_size
            crc_start_addr = self.imgs[idx].crc_start_addr
            if ( (pre_crc_start_addr + pre_crc_size) > crc_start_addr ):
                print(f'image%x start=%x size=%x overlapped with image%x start=%x'
                        %(idx-1, pre_crc_start_addr, pre_crc_size, idx, crc_start_addr))
                exit(0)
            #check_addr(self.imgs[idx - 1], self.imgs[idx])

    def test(self):
        data = 1
        content = data.to_bytes(1, "big")
        f = open('t.bin', "wb+")
        for i in range(4096):
            f.write(content)

        f.seek(0x10240)
        f.write(content)
        f.flush()
        f.close()

    def merge_image(self):
        f = open(self.output_file_name, 'wb+')
        for idx in range(self.imgs_cnt):
            img = self.imgs[idx]
            img.add_crc()
            print(f'merge image{idx} start=%x' %(img.crc_start_addr))
            print(img.crc_buf)
            f.seek(img.crc_start_addr)
            f.write(img.crc_buf)

        f.flush()
        f.close()

def main():
    img = images("img_config.json", "all.bin")
    img.merge_image()

if __name__ == "__main__":
    main()
