import struct
import hid

import time
import rumps
import os

LG_MONITOR_CONTROL_VID = 0x043E
LG_MONITOR_CONTROL_PID = 0x9A39
LG_MONITOR_DDCCI_I2C_ADDR = 0x37

# 0 - no split
# 1 - left-right half and half
# 2 - top-bottom half and half
# 3 - left-right 3/4 and 1/4
# 4 - left-right 1/4 and 3/4
# 5 - left-right 2/3 and 1/3
# 6 - 1:1 PIP top left
# 7 - 1:1 PIP top right
# 8 - 1:1 PIP bottom left
# 9 - 1:1 PIP bottom right
# A - change PIP ratio to 16:9
# B - three-way, center slightly larger
# C - also three-way?
# D - Quad split
# E - invalid
LG_SPLIT_NONE = 0x0
LG_SPLIT_LEFT_RIGHT_HALF_HALF = 0x1
LG_SPLIT_TOP_BOTTOM = 0x2
LG_SPLIT_LEFT_RIGHT_3_4__1_4 = 0x3
LG_SPLIT_LEFT_RIGHT_1_4__3_4 = 0x4
LG_SPLIT_LEFT_RIGHT_2_3__1_3 = 0x5
LG_SPLIT_SQUARE_PIP_TOP_LEFT = 0x6
LG_SPLIT_SQUARE_PIP_TOP_RIGHT = 0x7
LG_SPLIT_SQUARE_PIP_BOTTOM_LEFT = 0x8
LG_SPLIT_SQUARE_PIP_BOTTOM_RIGHT = 0x9
LG_SPLIT_PIP_16_9 = 0xA
LG_SPLIT_THREE_WAY_SPLIT = 0xB
LG_SPLIT_THREE_WAY_SPLIT_2 = 0xC
LG_SPLIT_QUAD_SPLIT = 0xD
LG_SPLIT_FIX_AUDIO = 0xE

# Split sound source
LG_SOUND_MAIN = 0
LG_SOUND_SUB = 1

# LG monitor enum
LG_MONITOR_HDMI1 = 0
LG_MONITOR_HDMI2 = 1
LG_MONITOR_DP1 = 2
LG_MONITOR_USB_C = 3

# DDC monitor enum
MONITOR_AUTO = 0x0
MONITOR_HDMI1 = 0x90
MONITOR_HDMI2 = 0x91
MONITOR_DP1 = 0xd0
MONITOR_DP2 = 0xd1
MONITOR_DP3 = 0xd2
MONITOR_USB_C = 0xd2

# Globals
VCP_D7_SET_1 = 0x002edc61
VCP_D7_SET_2 = 0x002ee2e8
VCP_D7_SET_3 = 0x002ee2f9
VCP_D7_SET_4 = 0x002ee2cb
VCP_D7_SET_5 = 0x002ee2b2

VCP_D7_GET_1 = 0x0029ef6f

BIG_U32_ADDR = 0x0053b5c0

VCP_83_GET_1 = 0x0029f24b

DDC_50_D1_1 = 0x00297c45
DDC_50_D5_1 = 0x002977f9
DDC_50_DEFAULT_CASE = 0x00297778
DDC_50_SWITCHTABLE = 0x003a3278

SPLIT_5_ADDR = 0x002ee2de
SPLIT_3_ADDR = 0x002ee2fa

MONITOR_INFO_STRUCT = 0x005d5928

device = None

#
# Helpers
#
def msg_checksum(msg):
    sum = 0x6E^0x50
    for i in range(0, len(msg)):
        sum ^= msg[i]
    return sum

def msg_add_checksum(msg):
    sum = 0x6E
    for i in range(8, len(msg)):
        sum ^= msg[i]
    msg += [sum]
    return msg

def msg_add_checksum_2(msg):
    sum = 0x6E
    for i in range(0, len(msg)):
        sum ^= msg[i]
    msg += [sum]
    return msg

def hex_dump(b, prefix=""):
    p = prefix
    b = bytes(b)
    for i in range(0, len(b)):
        if i != 0 and i % 16 == 0:
            print (p)
            p = prefix
        p += ("%02x " % b[i])
    print (p)
    print ("")

class LgUsbMonitorControl:

    def __init__(self):
        # USB
        self.has_usb = False
        self.dev = None
        self.ep_in = None
        self.ep_out = None

    def init_usb(self):
        self.dev = hid.device()
        self.dev.open(LG_MONITOR_CONTROL_VID, LG_MONITOR_CONTROL_PID)

        self.has_usb = True

    def fix_connection(self):
        self.init_usb()

        # Drain anything waiting?
        for i in range(0,10):
            self.read_raw(0x40, 10)

        run_patches()

    def send_raw(self, pkt):
        if not self.has_usb:
            return

        try:
            self.dev.write(bytes(pkt + [0] * (0x40 - len(pkt))))
        except Exception as e:
            print ("Failed to write", e)
            self.fix_connection()

    def read_raw(self, amt=0x40, timeout=200):
        if not self.has_usb:
            return

        try:
            return bytes(self.dev.read(amt, timeout))
        except Exception as e:
            print ("Failed to read", e)
            self.fix_connection()

        return []

    def send_to_i2c(self, addr, data):
        wrapped = [0x08, 0x01, 0x55, 0x03, len(data), 0x00, 0x03]
        wrapped += [addr]
        wrapped += data
        #hex_dump(wrapped)
        self.send_raw(wrapped)

    def begin_read_from_i2c(self, addr, to_read):
        wrapped = [0x08, 0x02, 0x55, 0x04, to_read, 0x00, 0xb]
        wrapped += [addr]
        #hex_dump(wrapped)
        self.send_raw(wrapped)

    def read_from_i2c(self, addr, expected_back):
        data = bytes()

        if expected_back <= 0:
            return data

        time.sleep(0.01)
        needed = expected_back
        while needed > 0:
            to_read = 0x10
            if to_read > needed:
                to_read = needed
            self.begin_read_from_i2c(addr, to_read)
        
            data_tmp = self.read_raw(0x100)

            amt_gotten = data_tmp[0] - 4
            needed -= amt_gotten
            
            data += data_tmp[4:4+amt_gotten]

        return data
    
    def wrap_send_vcp_2(self, data, expected_back=0xb):
        return self.wrap_send_vcp_4(data, expected_back, 0x51)
    
    def wrap_send_vcp_3(self, data, expected_back=0xb):
        return self.wrap_send_vcp_4(data, expected_back, 0x50)
    
    def wrap_send_vcp_4(self, data, expected_back=0xb, which_device=0x51):
        data_len = len(data)
        data = [0x00 | data_len] + data
        data = [which_device] + data
        data = msg_add_checksum_2(data)

        self.send_to_i2c(LG_MONITOR_DDCCI_I2C_ADDR, data)
        
        return self.read_from_i2c(LG_MONITOR_DDCCI_I2C_ADDR, expected_back)
    
    def get_vcp(self, idx):
        for i in range(0, 1000):
        
            data = self.wrap_send_vcp_2([0x01, idx])
            
            #hex_dump(data)
            if (len(data) < 0xb):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len =len(data)-1-2

            test = msg_checksum(data[1:1+data_len+2])

            if (test == 0 and data[2] == 2 and data[4] == idx):
                return data[9] | data[8] << 8
            time.sleep(0.1)
        return -1
    
    def set_vcp(self, idx, val, val2=0):
        for i in range(0, 10):
        
            data = self.wrap_send_vcp_2([0x03, idx,(val >> 8) & 0xFF,(val >> 0) & 0xFF])
            
            #hex_dump(data)
            if (len(data) < 0xb):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len =len(data)-1-2

            test = msg_checksum(data[1:1+data_len+2])

            if (test == 0 and data[4] == idx):
                return data[9]
            time.sleep(0.1)
        return -1

    def lg_special(self, idx, val):
        for i in range(0, 10):

            data = self.wrap_send_vcp_3([0x03,idx,(val >> 8) & 0xFF, val & 0xFF], 0x26)

            device.read_raw()
            #hex_dump(data)
            if (len(data) < 0x26):
                #hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len = len(data)-1-2

            return data
        return bytes([])

    def lg_special_u32(self, idx, val):
        for i in range(0, 10):

            data = self.wrap_send_vcp_3(list(struct.pack("<BB", 0x03, idx))+list(struct.pack(">L",val)), 0x26)

            #hex_dump(data)
            if (len(data) < 0x26):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len = len(data)-1-2

            return data
        return bytes([0,0,0,0,0,0,0,0,0,0])

    def lg_special_u32_u8(self, idx, val, val2):
        for i in range(0, 10):

            data = self.wrap_send_vcp_3(list(struct.pack("<BB", 0x03, idx))+list(struct.pack(">LB",val,val2)), 0x26)

            #hex_dump(data)
            if (len(data) < 0x26):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len =len(data)-1-2

            return data
        return bytes([0,0,0,0,0,0,0,0,0,0])

    def lg_special_f3(self, val):
        for i in range(0, 1):
            data = self.wrap_send_vcp_4([0xf3,(val >> 8) & 0xFF, val & 0xFF], 0x26)

        hex_dump(data)
        return data

    def lg_special_cc_data(self, idx, val):
        data = self.wrap_send_vcp_4([0xcc,idx] + val, 0)
        return data
    
    def lg_special_cc_u32(self, idx, val):
        data = self.wrap_send_vcp_4([0xcc,idx,val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >>24) & 0xFF], 0)
        return data
    
    # Not atomic
    def lg_arbwrite_str16(self, addr, val):
        self.lg_arbwrite(addr, list(val.encode("utf-16"))[2:] + [0,0])
    
    def lg_arbwrite_u32(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack("<L", val)))
    
    def lg_arbwrite_u16(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack("<H", val)))
    
    def lg_arbwrite_u8(self, addr, val):
        self.lg_arbwrite(addr, [val & 0xFF])
    
    def lg_arbwrite_u32_be(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack(">L", val)))

    def lg_arbwrite_u24_be(self, addr, val):
        self.lg_arbwrite_u16_be(addr, val>>8)
        self.lg_arbwrite_u8(addr+2, val & 0xFF)
        
    def lg_arbwrite_u16_be(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack(">H", val)))
    
    def lg_arbwrite(self, addr, val):
        self.lg_special_cc_u32(0xf6, addr)
        self.lg_special_cc_u32(0xf6, addr)
        self.lg_special_cc_data(0xf4, val)

    # Atomic
    def my_arbwrite_str16(self, addr, val):
        self.my_arbwrite(addr, list(val.encode("utf-16"))[2:] + [0,0])
    
    def my_arbwrite_u32(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack("<L", val)))
    
    def my_arbwrite_u16(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack("<H", val)))
    
    def my_arbwrite_u8(self, addr, val):
        self.my_arbwrite(addr, [val & 0xFF])
    
    def my_arbwrite_u32_be(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack(">L", val)))

    def my_arbwrite_u24_be(self, addr, val):
        self.my_arbwrite_u16_be(addr, val>>8)
        self.my_arbwrite_u8(addr+2, val & 0xFF)
        
    def my_arbwrite_u16_be(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack(">H", val)))
    
    def my_arbwrite(self, addr, val):
        for i in range(0, len(val)):
            self.lg_special_u32_u8(0xd5, addr+i, val[i])

    # Also atomic
    def lg_arbread_u32(self, addr):
        return struct.unpack("<L", bytes(self.lg_arbread_data(addr, 4)))[0]

    def lg_arbread_u16(self, addr):
        return struct.unpack("<H", bytes(self.lg_arbread_data(addr, 2)))[0]

    def lg_arbread_u32_be(self, addr):
        return struct.unpack(">L", bytes(self.lg_arbread_data(addr, 4)))[0]

    def lg_arbread_u16_be(self, addr):
        return struct.unpack(">H", bytes(self.lg_arbread_data(addr, 2)))[0]

    def lg_arbread_u8(self, addr):
        data = device.lg_special_u32(0xd1, addr)
        val = data[1]
        while data[0] != 0x82:
            data = device.lg_special_u32(0xd1, addr)
            val = data[1]
        return val

    def lg_arbread_data(self, addr, data_len):
        vals = []
        for i in range(0, data_len):
            val = self.lg_arbread_u8(addr+i)
            #print (hex(i),hex(val))
            vals += [val]
        return vals

    def lg_get_cur_monitor_sound(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2b5)

    def lg_set_cur_monitor_sound(self, val):
        self.my_arbwrite_u8(MONITOR_INFO_STRUCT+0x2b5, val & 0xFF)

    def lg_get_cur_primary(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2d0)

    def lg_get_cur_secondary(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2d1)

    def lg_set_cur_primary(self, val):
        self.my_arbwrite_u8(MONITOR_INFO_STRUCT+0x2d0, val & 0xFF)

    def lg_set_cur_secondary(self, val):
        self.my_arbwrite_u8(MONITOR_INFO_STRUCT+0x2d1, val & 0xFF)

    def lg_set_split(self, val):
        if val > LG_SPLIT_FIX_AUDIO:
            return
        if self.lg_get_split() == val:
            return

        self.set_vcp(0xd7, val)

    def lg_get_split(self):
        return self.get_vcp(0xd7)

    def lg_monitor_to_ddc(self, val):
        my_lut = [MONITOR_HDMI1, MONITOR_HDMI2, MONITOR_DP1, MONITOR_USB_C, MONITOR_USB_C]
        if val >= len(my_lut):
            return 0
        return my_lut[val]

    def lg_set_primary_input(self, val):
        device.lg_special(0xF4, self.lg_monitor_to_ddc(val))

    def lg_reset_monitor(self):
        device.lg_special(0xF5, 0)


# List of cool characters
# ■ □
# ⊟
# ◱ ◰

@rumps.timer(1)
def fix_displays_and_mouse(sender):
    os.system("fix_displays_and_mouse.sh")
    device.get_vcp(0x10) # heartbeat to trigger USB fixups

    #for i in range(0, 0x10):
    #    print (hex(i), hex(device.lg_arbread_u32(0x005445d4+i*0x24)))
    #print (hex(device.lg_arbread_u32(0x00544a5c)))
    

    # Sometimes writes get dropped...
    # The CC commands do not return *anything* so there's no way to know
    # until the arbread patch goes through.
    for i in range(0, 10):
        run_patches()

        val = device.lg_arbread_u32_be(VCP_D7_SET_1+0)
        if val == 0xd140326a:
            break

class AwesomeStatusBarApp(rumps.App):
    @rumps.clicked("□\tNo split")
    def single_pane(self, _):
        #device.lg_set_cur_monitor_sound(0)
        #device.lg_set_split(0x1)
        device.lg_set_split(LG_SPLIT_NONE)
        print(device.lg_get_split())

    @rumps.clicked("⊟\tTop-Bottom")
    def double_pane(self, _):
        device.lg_set_split(LG_SPLIT_TOP_BOTTOM)
        print(device.lg_get_split())

    @rumps.clicked("⇆\tSwap sound sources")
    def swap_sound_sources(self, _):
        cur = device.lg_get_cur_monitor_sound()
        swap_lut = [1,0]
        next_source = swap_lut[cur & 1]
        device.lg_set_cur_monitor_sound(next_source)
        print (next_source)
        device.lg_set_split(LG_SPLIT_FIX_AUDIO)
        #print(device.get_vcp(0xd7))

    @rumps.clicked("⊟⇆\tSwap splits")
    def swap_splits(self, _):
        cur = device.lg_get_cur_monitor_sound()
        swap_lut = [1,0]
        next_source = swap_lut[cur & 1]
        device.lg_set_cur_monitor_sound(next_source)

        cur_primary = device.lg_get_cur_primary()
        cur_secondary = device.lg_get_cur_secondary()

        device.lg_set_primary_input(cur_secondary)

    @rumps.clicked("⊟\tSplatoon")
    def splatoon(self, _):
        device.lg_set_cur_monitor_sound(LG_SOUND_SUB)
        device.lg_set_cur_primary(LG_MONITOR_USB_C)
        device.lg_set_cur_secondary(LG_MONITOR_HDMI2)
        device.lg_set_split(LG_SPLIT_TOP_BOTTOM)

#
# Verifying that my AEON R2 SLEIGH is correct
#
def test_conditional(val_a, val_b):
    '''
switchD_0029eca1::caseD_83                      XREF[2]:     0029eca1(j), 003a3f94(*)  
        0029f24b 50 60 ff        bn.ori     r3,r0,0xff
        0029f24e 50 80 ff        bn.ori     r4,r0,0xff
        0029f251 d0 60 00 38     bg.blei    r3,0x0,LAB_0029f258
        0029f255 50 60 00        bn.ori     r3,r0,0x0
                             LAB_0029f258                                    XREF[1]:     0029f251(j)  
        0029f258 18 61 15        bn.sbz     0x15(r1),r3
        0029f25b 40 00 04        bn.nop

    '''
    setflag_bg = False
    setflag_bn = False
    opcode_bn = True
    branch_bn = False
    immediate = True
    if val_a & 0x10:
        val_a |= 0xFFFFFFE0
    if val_b & 0x10:
        val_b |= 0xFFFFFFE0

    device.my_arbwrite_u24_be(VCP_83_GET_1+0, 0x1c6000 | (val_a & 0xFF)) # bn.addi r3,r0,immA
    device.my_arbwrite_u24_be(VCP_83_GET_1+3, 0x1c8000 | (val_b & 0xFF)) # bn.addi r3,r0,immB
    which = 0
    if setflag_bg:
        if val_b & 0x10:
            val_b |= 0xFFFFFFE0
        device.my_arbwrite_u32_be(VCP_83_GET_1+6, 0xc0600000 | ((val_b & 0xffff) << 5) | (which << 1)) # bg.sfeqi r3,0
        device.my_arbwrite_u24_be(VCP_83_GET_1+10, 0x486103) # bn.cmovi     r3,0x1,0x0
    elif setflag_bn:
        if val_b & 0x10:
            val_b |= 0xFFFFFFE0
        device.my_arbwrite_u24_be(VCP_83_GET_1+6, 0x5c6001 | ((val_b & 0xff) << 5) | (which << 1)) # bn.sfeqi r3,0
        device.my_arbwrite_u24_be(VCP_83_GET_1+9, 0x486103) # bn.cmovi     r3,0x1,0x0
    elif branch_bn:
        if immediate:
            device.my_arbwrite_u24_be(VCP_83_GET_1+6, 0x246018 | ((val_b & 0x7) << 10) | which) # bn.blesi r3,val,LAB_0029f258
            device.my_arbwrite_u24_be(VCP_83_GET_1+9, 0x506055) # bn.ori     r3,r0,0x55
        else:
            device.my_arbwrite_u24_be(VCP_83_GET_1+6, 0x206018 | which) # bg.bles r3,r4,LAB_0029f258
            device.my_arbwrite_u24_be(VCP_83_GET_1+9, 0x506055) # bn.ori     r3,r0,0x55
    elif opcode_bn:
        #device.my_arbwrite_u24_be(VCP_83_GET_1+6, 0x446320 | which) # bn.op... r3,r3,r4
        device.my_arbwrite_u24_be(VCP_83_GET_1+6, 0x146700 | which) # bn.op... r3,r3,r4
        device.my_arbwrite_u24_be(VCP_83_GET_1+9, 0x400004) # nop
        #device.my_arbwrite_u24_be(VCP_83_GET_1+9, 0x486103) # bn.cmovi     r3,0x1,0x0
    else:
        if immediate:
            device.my_arbwrite_u32_be(VCP_83_GET_1+6, 0xd0600038 | ((val_b & 0x1F) << 16) | which) # bg.blesi r3,val,LAB_0029f258
            device.my_arbwrite_u24_be(VCP_83_GET_1+10, 0x506055) # bn.ori     r3,r0,0x55
        else:
            device.my_arbwrite_u32_be(VCP_83_GET_1+6, 0xd4640038 | which) # bg.bles r3,r4,LAB_0029f258
            device.my_arbwrite_u24_be(VCP_83_GET_1+10, 0x506055) # bn.ori     r3,r0,0x55
    
    if not setflag_bn and not branch_bn and not opcode_bn:
        device.my_arbwrite_u24_be(VCP_83_GET_1+13, 0x186115) # bn.sbz     0x15(r1),r3
        device.my_arbwrite_u24_be(VCP_83_GET_1+16, 0x400004)
        device.my_arbwrite_u24_be(VCP_83_GET_1+19, 0x400004)
    else:
        device.my_arbwrite_u24_be(VCP_83_GET_1+12, 0x186115) # bn.sbz     0x15(r1),r3
        device.my_arbwrite_u16_be(VCP_83_GET_1+15, 0x8001)
        device.my_arbwrite_u16_be(VCP_83_GET_1+17, 0x8001)
        device.my_arbwrite_u24_be(VCP_83_GET_1+19, 0x400004)
        



    # Attempt to get the caches to stahp
    scalar_fw_version = device.lg_special(0xc9,0)[0:0+3]
    model_str = bytes(device.lg_special(0xca,0)[0:0+7])

    val = device.get_vcp(0x83)

    if setflag_bn or setflag_bg or opcode_bn:
        return val
    else:
        return 0 if val == 0x55 else 1

def patch_atomic_read():
    device.lg_arbwrite_u24_be(DDC_50_D1_1+0,  0x106a04) # bn.lbz    r3,0x4(r10)
    device.lg_arbwrite_u24_be(DDC_50_D1_1+3,  0x4c6340) # bn.slli   r3,r3,8
    device.lg_arbwrite_u24_be(DDC_50_D1_1+6,  0x108a05) # bn.lbz    r4,0x5(r10)
    device.lg_arbwrite_u24_be(DDC_50_D1_1+9,  0x446325) # bn.or     r3,r3,r4
    device.lg_arbwrite_u24_be(DDC_50_D1_1+12, 0x4c6340) # bn.slli   r3,r3,8
    device.lg_arbwrite_u24_be(DDC_50_D1_1+15, 0x108a06) # bn.lbz    r4,0x6(r10)
    device.lg_arbwrite_u24_be(DDC_50_D1_1+18, 0x446325) # bn.or     r3,r3,r4
    device.lg_arbwrite_u24_be(DDC_50_D1_1+21, 0x4c6340) # bn.slli   r3,r3,8
    device.lg_arbwrite_u24_be(DDC_50_D1_1+24, 0x108a07) # bn.lbz    r4,0x7(r10)
    device.lg_arbwrite_u24_be(DDC_50_D1_1+27, 0x446325) # bn.or     r3,r3,r4
    device.lg_arbwrite_u24_be(DDC_50_D1_1+30, 0x106300) # bn.lbz    r3,0(r3)
    device.lg_arbwrite_u24_be(DDC_50_D1_1+33, 0x187201) # bn.sbz    0x1(r18),r3
    device.lg_arbwrite_u24_be(DDC_50_D1_1+36, 0x506082) # bn.ori    r3,r0,0x82
    device.lg_arbwrite_u24_be(DDC_50_D1_1+39, 0x2FFB0E) # bn.j      LAB_0029777a

def patch_atomic_write():
    device.lg_arbwrite_u24_be(DDC_50_D5_1+0,  0x106a04) # bn.lbz    r3,0x4(r10)
    device.lg_arbwrite_u24_be(DDC_50_D5_1+3,  0x4c6340) # bn.slli   r3,r3,8
    device.lg_arbwrite_u24_be(DDC_50_D5_1+6,  0x108a05) # bn.lbz    r4,0x5(r10)
    device.lg_arbwrite_u24_be(DDC_50_D5_1+9,  0x446325) # bn.or     r3,r3,r4
    device.lg_arbwrite_u24_be(DDC_50_D5_1+12, 0x4c6340) # bn.slli   r3,r3,8
    device.lg_arbwrite_u24_be(DDC_50_D5_1+15, 0x108a06) # bn.lbz    r4,0x6(r10)
    device.lg_arbwrite_u24_be(DDC_50_D5_1+18, 0x446325) # bn.or     r3,r3,r4
    device.lg_arbwrite_u24_be(DDC_50_D5_1+21, 0x4c6340) # bn.slli   r3,r3,8
    device.lg_arbwrite_u24_be(DDC_50_D5_1+24, 0x108a07) # bn.lbz    r4,0x7(r10)
    device.lg_arbwrite_u24_be(DDC_50_D5_1+27, 0x446325) # bn.or     r3,r3,r4
    device.lg_arbwrite_u24_be(DDC_50_D5_1+30, 0x108a08) # bn.lbz    r4,0x8(r10)
    device.lg_arbwrite_u24_be(DDC_50_D5_1+33, 0x188300) # bn.sbz    0(r3),r4
    device.lg_arbwrite_u24_be(DDC_50_D5_1+36, 0x506082) # bn.ori    r3,r0,0x82
    device.lg_arbwrite_u16_be(DDC_50_D5_1+39, 0x935a) # bn.j      LAB_0029777a

def modify_50_switchtable_case(idx, val):
    if idx < 0x10:
        return
    device.my_arbwrite_u32(DDC_50_SWITCHTABLE+((idx-0x10)*4), val)

def patch_d7_pbp_pip():
    # We keep the 0x0 extra bits, but make it the same as 0x1 was before
    device.my_arbwrite_u32_be(VCP_D7_SET_1+0, 0xd140326a) # bg.beqi    r10,0x0,LAB_002ee2ae

    # We make 0xe apply sound swaps
    device.my_arbwrite_u32_be(VCP_D7_SET_1+4, 0xd14e3332) # bg.beqi    r10,0xe,LAB_002ee2cb

    # And everything else is just directly raw
    device.my_arbwrite_u32_be(VCP_D7_SET_1+8, 0xe4000cfb) # bg.j LAB_002ee2e6
    device.my_arbwrite_u16_be(VCP_D7_SET_2+0, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_2+2, 0x8001) # bt.nop

    device.my_arbwrite_u16_be(VCP_D7_SET_2+0, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_2+2, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_2+4, 0x8001) # bt.nop

    # Use the raw value
    device.my_arbwrite_u16_be(VCP_D7_SET_3+0, 0x886a) # bt.mov r3,r10

    # 0xE sound swap stuff
    device.my_arbwrite_u32_be(VCP_D7_SET_4+0,  0xe7f7ec0e) # bg.jal     get_which_monitor_has_sound 
    device.my_arbwrite_u32_be(VCP_D7_SET_4+4,  0xe7f826f4) # bg.jal     sets_which_monitor_has_sound
    device.my_arbwrite_u16_be(VCP_D7_SET_4+8,  0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_4+10, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_4+12, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_4+14, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_4+16, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_4+18, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_4+20, 0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_SET_4+22, 0x8001) # bt.nop

    # Make 0x0 the same as 0x1 was before
    device.my_arbwrite_u16_be(VCP_D7_SET_5+0,  0x9860) # bt.movi r3,0

    #
    # Patch VCP 0xD7 getter to just send raw split values
    #
    device.my_arbwrite_u16_be(VCP_D7_GET_1+0,  0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_GET_1+2,  0x8001) # bt.nop
    device.my_arbwrite_u16_be(VCP_D7_GET_1+12, 0x8883) # bt.mov r4,r3

def run_patches():

    if device.lg_arbread_u16_be(DDC_50_D5_1+41) != 0x55aa:
        #
        # Patch DDC2AB (0x50) 0xD1 to be an atomic u8 read
        # This is required to prevent random crashes when reading/writing, if the
        # LG arbwrite pointer randomly changes or is reset to 0 due to sleep.
        #
        while device.lg_arbread_u16_be(DDC_50_D1_1+0) != 0x106a:
            for i in range(0, 2):
                patch_atomic_read()

        #
        # Patch DDC2AB (0x50) 0xD5 to be an atomic u8 write
        # This is required to prevent random crashes when reading/writing, if the
        # LG arbwrite pointer randomly changes or is reset to 0 due to sleep.
        #
        while device.lg_arbread_u16_be(DDC_50_D5_1+41) != 0x55aa:
            for i in range(0, 2):
                patch_atomic_write()

            device.my_arbwrite_u16_be(DDC_50_D5_1+41, 0x55aa)

    # These got clobbered by the patches.
    modify_50_switchtable_case(0x68, DDC_50_DEFAULT_CASE)
    modify_50_switchtable_case(0x69, DDC_50_DEFAULT_CASE)
    modify_50_switchtable_case(0x75, DDC_50_DEFAULT_CASE)
    modify_50_switchtable_case(0xd6, DDC_50_DEFAULT_CASE)
    modify_50_switchtable_case(0xd7, DDC_50_DEFAULT_CASE)

    #
    # Patch VCP 0xD7 setter to just send raw split values:
    #
    patch_d7_pbp_pip()

    # Unlock all of the PIP/PBP menu options that are useful (not the vertical 3-ways)
    device.my_arbwrite_u24_be(0x002951dc, 0x1c6000 | (0x3 & 0xFF)) # ori r3,r0,val
    device.my_arbwrite_u24_be(0x00295c02, 0x1c6000 | (0x0 & 0xFF)) # ori r3,r0,val
    device.my_arbwrite_u24_be(0x00295c28, 0x1c6000 | (0x0 & 0xFF)) # ori r3,r0,val

    # disp overclock?
    #device.my_arbwrite_u24_be(0x002957a5, 0x1c6000 | (0x0 & 0xFF)) # ori r3,r0,val
    #device.my_arbwrite_u24_be(0x002957d3, 0x1c6000 | (0x0 & 0xFF)) # ori r3,r0,val
    

    # Choose different tool menus
    #device.my_arbwrite_u24_be(0x002d2487, 0x1c8000 | (0x8 & 0xFF))

    # Override PBP menu to any other menu
    #device.my_arbwrite_u8(0x002b9155, 0xa9)

    

    #device.my_arbwrite_u16_be(0x002bc283, 0x98eb);


if __name__ == "__main__":
    device = LgUsbMonitorControl()
    device.init_usb()

    scalar_fw_version = device.lg_special(0xc9,0)[0:0+3]
    model_str = bytes(device.lg_special(0xca,0)[0:0+7])

    if scalar_fw_version != bytes([0x82, 0x03, 0x30]) or model_str != b"28MQ780":
        print("Please read the README and don't run random mempoke scripts on your monitor.")
        print("Scalar version:", scalar_fw_version)
        print("Model:", model_str)
        exit(1)

    # Reset just to make sure the monitor is in a clean state,
    # unless we detect our atomic arbread working
    if device.lg_arbread_u16_be(DDC_50_D5_1+41) != 0x55aa:
        #device.lg_reset_monitor()
        time.sleep(1)

    # Sometimes writes get dropped...
    # The CC commands do not return *anything* so there's no way to know
    # until the arbread patch goes through.
    for i in range(0, 10):
        run_patches()

        val = device.lg_arbread_u32_be(VCP_D7_SET_1+0)
        if val == 0xd140326a:
            print ("Arbread test successful.")
            break
        else:
            print ("Arbread test failed...", hex(val), "!=", hex(0xd140326a))
            if i == 9:
                print ("Exiting.")
                device.lg_reset_monitor()
                exit(1)
            print ("Trying again...")

    # 1 = input?
    # 2 = accessibility menu
    # 3 = ?
    # 4 = ?
    # 5 = service menu?
    #device.my_arbwrite_u32_be(0x0026561a, 0xffffffff)
    #print(hex(device.lg_arbread_u32(0x0042ac30)))
    #device.my_arbwrite_u16_be(0x002daed3, 0x9000)

    '''
    for i in range(0, 0x2):
        for j in range(0, 0x20):
            val = test_conditional(i, j)
            print (hex(i), hex(j), hex(val))

    for i in range(0x1E, 0x20):
        for j in range(0, 0x20):
            val = test_conditional(i, j)
            print (hex(i), hex(j), hex(val))
            
    exit(1)
    '''

    '''
    print ("Fetch 1")
    data_1 = device.lg_arbread_data(MONITOR_INFO_STRUCT, 0x1000)
    hex_dump(data_1)
    print ("Fetch 1 done")
    time.sleep(10)
    print ("Fetch 2")
    data_2 = device.lg_arbread_data(MONITOR_INFO_STRUCT, 0x1000)
    print ("Fetch 2 done")

    for i in range(0, 0x1000):
        if data_1[i] != data_2[i]:
            print(hex(i) + ": " + hex(data_1[i]) + " " + hex(data_2[i]))

    #device.my_arbwrite_u8(SPLIT_5_ADDR, 0x60 | 0x2)
    '''

    global_namespace_timer = rumps.Timer(fix_displays_and_mouse, 4)
    global_namespace_timer.start()
    AwesomeStatusBarApp("🦊").run()

    
    #device.my_arbwrite_str16(QUICK_SETTINGS_ADDR, "lol")
    #device.my_arbwrite_str16(QUICK_SETTINGS_ADDR_2, "*hacker voice* I'm in")