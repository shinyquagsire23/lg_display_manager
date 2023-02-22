import struct
import hid

import time
import rumps
import os

LG_MONITOR_CONTROL_VID = 0x043E
LG_MONITOR_CONTROL_PID = 0x9A39

# 0 - no split
# 1 - left-right half and half
# 2 - top-bottom half and half
# 3 - left-right 3/4 and 1/4
# 4 - left-right 1/4 and 3/4
# 5 - left-right 23 and 1/3
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

VCP_52_GET_1 = 0x0029f033
VCP_52_GET_2 = 0x0029f02c
BIG_U32_ADDR = 0x0053b5c0

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

    def send_raw(self, pkt):
        if not self.has_usb:
            return

        try:
            self.dev.write(bytes(pkt + [0] * (0x40 - len(pkt))))
        except Exception as e:
            print ("Failed to write", e)

    def read_raw(self, amt=0x40):
        if not self.has_usb:
            return

        try:
            return bytes(self.dev.read(amt, 200))
        except Exception as e:
            print ("Failed to read", e)
        return []

    def wrap_send_vcp(self, data):
        wrapped = [0x08, 0x01, 0x55, 0x03, 0x00, 0x00, 0x03, 0x37]
        
        data = [0x51] + data
        data = msg_add_checksum_2(data)
        wrapped[4] += len(data)
        wrapped += data
        
        #hex_dump(wrapped)

        self.send_raw(wrapped)
        wrapped[1] = 0x02
        wrapped[3] = 0x04
        wrapped[4] = 0x0b
        wrapped[6] = 0x0b
        self.send_raw(wrapped)
        #hex_dump(wrapped)

        return wrapped
    
    def wrap_send_vcp_2(self, data, expected_back=0xb):
        wrapped = [0x08, 0x01, 0x55, 0x03, 0x00, 0x00, 0x03, 0x37]
        
        data_len = len(data)
        data = [0x80 | data_len] + data
        data = [0x51] + data
        data = msg_add_checksum_2(data)
        wrapped[4] += len(data)
        wrapped += data
        
        #hex_dump(wrapped)

        self.send_raw(wrapped)
        wrapped[1] = 0x02
        wrapped[3] = 0x04
        wrapped[4] = expected_back
        wrapped[6] = 0x0b
        self.send_raw(wrapped)
        #hex_dump(wrapped)

        return wrapped
    
    def wrap_send_vcp_3(self, data, expected_back=0xb):
        wrapped = [0x08, 0x01, 0x55, 0x03, 0x00, 0x00, 0x03, 0x37]
        
        data_len = len(data)
        data = [0x80 | data_len] + data
        data = [0x50] + data
        data = msg_add_checksum_2(data)
        wrapped[4] += len(data)
        wrapped += data
        
        #hex_dump(wrapped)

        self.send_raw(wrapped)
        wrapped[1] = 0x02
        wrapped[3] = 0x04
        wrapped[4] = expected_back
        wrapped[6] = 0x0b
        self.send_raw(wrapped)
        #hex_dump(wrapped)

        return wrapped
    
    def wrap_send_vcp_4(self, data, expected_back=0xb, which_device=0x51):
        wrapped = [0x08, 0x01, 0x55, 0x03, 0x00, 0x00, 0x03, 0x37]
        
        data_len = len(data)
        data = [0x00 | data_len] + data
        data = [which_device] + data
        data = msg_add_checksum_2(data)
        wrapped[4] += len(data)
        wrapped += data
        
        wrapped += [0]*(0x40-len(wrapped))
        
        #hex_dump(wrapped)

        self.send_raw(wrapped)
        data = bytes()

        if expected_back <= 0:
            return data

        time.sleep(0.01)
        needed = expected_back
        while needed > 0:
            to_read = 0x10
            if to_read > needed:
                to_read = needed
            wrapped[1] = 0x02
            wrapped[3] = 0x04
            wrapped[4] = to_read
            wrapped[6] = 0x0b
            self.send_raw(wrapped)
        
            data_tmp = self.read_raw(0x100)

            amt_gotten = data_tmp[0] - 4
            needed -= amt_gotten
            
            data += data_tmp[4:4+amt_gotten]

        return data
    
    def wrap_send_vcp_alt(self, data, sum):
        wrapped = [0x08, 0x01, 0x55, 0x03, 0x00, 0x00, 0x03, 0x37]
        
        data = [0x51] + data
        data = data + [sum]
        wrapped[4] += len(data)
        wrapped += data

        self.send_raw(wrapped)
        wrapped[1] = 0x02
        wrapped[3] = 0x04
        wrapped[4] = 0x0b
        wrapped[6] = 0x0b
        self.send_raw(wrapped)

        return wrapped

    def get_vcp(self, idx):
        for i in range(0, 1000):
        
            self.wrap_send_vcp_2([0x01, idx])
            
            data = self.read_raw()
            #hex_dump(data)
            if (len(data) < 8):
                hex_dump(data)
                continue
            
            data_len = data[5] & 0x7F
            if data_len > len(data)-5-2:
                data_len =len(data)-5-2

            test = msg_checksum(data[5:5+data_len+2])

            if (test == 0 and data[6] == 2 and data[8] == idx):
                return data[13] | data[12] << 8
            time.sleep(0.1)
        return -1
    
    def set_vcp(self, idx, val, val2=0):
        for i in range(0, 10):
        
            self.wrap_send_vcp_2([0x03, idx,(val >> 8) & 0xFF,(val >> 0) & 0xFF])
            
            data = self.read_raw()
            #hex_dump(data)
            if (len(data) < 8):
                hex_dump(data)
                continue
            
            data_len = data[5] & 0x7F
            if data_len > len(data)-5-2:
                data_len =len(data)-5-2

            test = msg_checksum(data[5:5+data_len+2])

            if (test == 0 and data[8] == idx):
                return data[13]
            time.sleep(0.1)
        return -1

    def lg_special(self, idx, val):
        for i in range(0, 10):

            self.wrap_send_vcp_3([0x03,idx,(val >> 8) & 0xFF, val & 0xFF], 0x26)

            data = device.read_raw()
            #hex_dump(data)
            if (len(data) < 8):
                hex_dump(data)
                continue
            
            data_len = data[5] & 0x7F
            if data_len > len(data)-5-2:
                data_len =len(data)-5-2

            if data[2] == 0x55:
                return data
        return bytes([])

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

    def lg_arbread_u32(self, addr):
        return struct.unpack("<L", bytes(self.lg_arbread_data(addr, 4)))[0]

    def lg_arbread_u16(self, addr):
        return struct.unpack("<H", bytes(self.lg_arbread_data(addr, 2)))[0]

    def lg_arbread_u32_be(self, addr):
        return struct.unpack(">L", bytes(self.lg_arbread_data(addr, 4)))[0]

    def lg_arbread_u16_be(self, addr):
        return struct.unpack(">H", bytes(self.lg_arbread_data(addr, 2)))[0]

    def lg_arbread_u8(self, addr):
        self.lg_special_cc_u32(0xf6, addr)
        self.lg_special_cc_u32(0xf6, addr)
        return self.get_vcp(0x52)

    def lg_arbread_data(self, addr, data_len):
        vals = []
        for i in range(0, data_len):
            #print (hex(i))
            vals += [self.lg_arbread_u8(addr+i)]
        return vals

    def lg_get_cur_monitor_sound(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2b5)

    def lg_set_cur_monitor_sound(self, val):
        self.lg_arbwrite_u8(MONITOR_INFO_STRUCT+0x2b5, val & 0xFF)

    def lg_get_cur_primary(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2d0)

    def lg_get_cur_secondary(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2d1)

    def lg_set_cur_primary(self, val):
        self.lg_arbwrite_u8(MONITOR_INFO_STRUCT+0x2d0, val & 0xFF)

    def lg_set_cur_secondary(self, val):
        self.lg_arbwrite_u8(MONITOR_INFO_STRUCT+0x2d1, val & 0xFF)

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

def run_patches():
    #
    # Patch VCP 0xD7 setter to just send raw split values:
    #
    # We keep the 0x0 extra bits, but make it the same as 0x1 was before
    device.lg_arbwrite_u32_be(VCP_D7_SET_1+0, 0xd140326a) # bg.beqi    r10,0x0,LAB_002ee2ae

    # We make 0xe apply sound swaps
    device.lg_arbwrite_u32_be(VCP_D7_SET_1+4, 0xd14e3332) # bg.beqi    r10,0xe,LAB_002ee2cb

    # And everything else is just directly raw
    device.lg_arbwrite_u32_be(VCP_D7_SET_1+8, 0xe4000cfb) # bg.j LAB_002ee2e6
    #device.lg_arbwrite_u32_be(VCP_D7_SET_2+0, 0xd4eac49a) # bg.beq    r7,r10,...
    device.lg_arbwrite_u16_be(VCP_D7_SET_2+0, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_2+2, 0x8001) # bt.nop

    device.lg_arbwrite_u16_be(VCP_D7_SET_2+0, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_2+2, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_2+4, 0x8001) # bt.nop

    # Use the raw value
    device.lg_arbwrite_u16_be(VCP_D7_SET_3+0, 0x886a) # bt.mov r3,r10

    # 0xE sound swap stuff
    device.lg_arbwrite_u32_be(VCP_D7_SET_4+0, 0xe7f7ec0e) # bg.jal     get_which_monitor_has_sound 
    device.lg_arbwrite_u32_be(VCP_D7_SET_4+4, 0xe7f826f4) # bg.jal     sets_which_monitor_has_sound
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+8, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+10, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+12, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+14, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+16, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+18, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+20, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_SET_4+22, 0x8001) # bt.nop

    # Make 0x0 the same as 0x1 was before
    device.lg_arbwrite_u16_be(VCP_D7_SET_5+0, 0x9860) # bt.movi r3,0

    #device.lg_arbwrite_u24_be(VCP_D7_SET_4+10, 0x400004) # bt.nop


    #
    # Patch VCP 0xD7 getter to just send raw split values
    #
    device.lg_arbwrite_u16_be(VCP_D7_GET_1+0, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_GET_1+2, 0x8001) # bt.nop
    device.lg_arbwrite_u16_be(VCP_D7_GET_1+12, 0x8883) # bt.mov r4,r3

    #
    # Patch VCP 0x52 getter to read the same value as the arbwrite
    #
    device.lg_arbwrite_u24_be(VCP_52_GET_2+0, 0x0c0104) # bn.sw      0x4(r1),r0,
    device.lg_arbwrite_u32_be(VCP_52_GET_1+0, 0xece7b5c2) # bg.lwz     r7,-0x4a40(r7)
    device.lg_arbwrite_u24_be(VCP_52_GET_1+4, 0x10e700) # bg.lbz     r7,0(r7)
    device.lg_arbwrite_u24_be(VCP_52_GET_1+7, 0x18e115) # bn.sbz     0x15(r1),r7

if __name__ == "__main__":
    device = LgUsbMonitorControl()
    device.init_usb()

    scalar_fw_version = device.lg_special(0xc9,0)[4:4+3]
    model_str = bytes(device.lg_special(0xca,0)[4:4+7])

    if scalar_fw_version != bytes([0x82, 0x03, 0x30]) or model_str != b"28MQ780":
        print("Please read the README and don't run random mempoke scripts on your monitor.")
        print("Scalar version:", scalar_fw_version)
        print("Model:", model_str)
        exit(1)

    # Reset just to make sure the monitor is in a clean state
    device.lg_reset_monitor()
    time.sleep(1)

    # Sometimes writes get dropped...
    # The CC commands do not return *anything* so there's no way to know
    # until the arbread patch goes through.
    for i in range(0, 10):
        run_patches()

        val = device.lg_arbread_u32_be(VCP_52_GET_1)
        if val == 0xece7b5c2:
            print ("Arbread test successful.")
            break
        else:
            print ("Arbread test failed...", hex(val), "!=", hex(0xece7b5c2))
            if i == 9:
                print ("Exiting.")
                device.lg_reset_monitor()
                exit(1)
            print ("Trying again...")

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

    #device.lg_arbwrite_u8(SPLIT_5_ADDR, 0x60 | 0x2)
    '''

    global_namespace_timer = rumps.Timer(fix_displays_and_mouse, 4)
    global_namespace_timer.start()
    AwesomeStatusBarApp("🦊").run()

    
    #device.lg_arbwrite_str16(QUICK_SETTINGS_ADDR, "lol")
    #device.lg_arbwrite_str16(QUICK_SETTINGS_ADDR_2, "*hacker voice* I'm in")