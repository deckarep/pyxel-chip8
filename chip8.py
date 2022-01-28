import pdb
import os
import io
import json
import pyxel
import random
import math

# https://tobiasvl.github.io/blog/write-a-chip-8-emulator/
# https://austinmorlan.com/posts/chip8_emulator/#the-instructions
# Clean rust implementation: https://github.com/ColinEberhardt/wasm-rust-chip8
# Clean Go implementation: https://massung.github.io/CHIP-8/
# Test ROM source: https://github.com/corax89/chip8-test-rom/blob/master/test_opcode.8o
FPS = 60

BANNER_MSG = "Chip 8 - Pyxelized - by deckarep - 2022"

TICKS_PER_UPDATE = 7

CHIP8_WIDTH = 64
CHIP8_HEIGHT = 32

MAX_STALLED_VM_CYCLES = 100

SCREEN_WIDTH = CHIP8_WIDTH * 3 # IDEA: multiply this number by 2 to get double width then put your CPU viewer on the right!
SCREEN_HEIGHT = CHIP8_HEIGHT * 3

CHIP8_X_OFFSET = SCREEN_WIDTH // 2 - CHIP8_WIDTH // 2
CHIP8_Y_OFFSET = (SCREEN_HEIGHT // 2 - CHIP8_HEIGHT // 2) - 20

# something about these colors makes collision detection work, changing them and we're screwed. (5 off, 1 on)
SCREEN_COLOR_OFF = 0
SCREEN_COLOR_ON = 3

ROM_STARTING_ADDRESS = 0x200
FONT_STARTING_ADDRESS = 0x50

VM_INSTRUCTIONS_PER_SECOND = 700
VM_ROMS_FOLDER = "roms/"
VM_MEMORY_SIZE = 4096

# Keypad       Keyboard
# +-+-+-+-+    +-+-+-+-+
# |1|2|3|C|    |1|2|3|4|
# +-+-+-+-+    +-+-+-+-+
# |4|5|6|D|    |Q|W|E|R|
# +-+-+-+-+ => +-+-+-+-+
# |7|8|9|E|    |A|S|D|F|
# +-+-+-+-+    +-+-+-+-+
# |A|0|B|F|    |Z|X|C|V|
# +-+-+-+-+    +-+-+-+-+

KEYS_OF_INTEREST = [
    pyxel.KEY_X,
    pyxel.KEY_1,
    pyxel.KEY_2,
    pyxel.KEY_3,
    pyxel.KEY_Q,
    pyxel.KEY_W,
    pyxel.KEY_E,
    pyxel.KEY_A,
    pyxel.KEY_S,
    pyxel.KEY_D,
    pyxel.KEY_Z,
    pyxel.KEY_C,
    pyxel.KEY_4,
    pyxel.KEY_R,
    pyxel.KEY_F,
    pyxel.KEY_V,
    pyxel.KEY_X
]

FONT_BYTE_SIZE = 5
FONT_DATA = [
    0xF0, 0x90, 0x90, 0x90, 0xF0, # 0
    0x20, 0x60, 0x20, 0x20, 0x70, # 1
    0xF0, 0x10, 0xF0, 0x80, 0xF0, # 2
    0xF0, 0x10, 0xF0, 0x10, 0xF0, # 3
    0x90, 0x90, 0xF0, 0x10, 0x10, # 4
    0xF0, 0x80, 0xF0, 0x10, 0xF0, # 5
    0xF0, 0x80, 0xF0, 0x90, 0xF0, # 6
    0xF0, 0x10, 0x20, 0x40, 0x40, # 7
    0xF0, 0x90, 0xF0, 0x90, 0xF0, # 8
    0xF0, 0x90, 0xF0, 0x10, 0xF0, # 9
    0xF0, 0x90, 0xF0, 0x90, 0x90, # A
    0xE0, 0x90, 0xE0, 0x90, 0xE0, # B
    0xF0, 0x80, 0x80, 0x80, 0xF0, # C
    0xE0, 0x90, 0x90, 0x90, 0xE0, # D
    0xF0, 0x80, 0xF0, 0x80, 0xF0, # E
    0xF0, 0x80, 0xF0, 0x80, 0x80  # F
]

class Chip8VM:
    def __init__(self):
        self.last_opcode = 0
        self.opcode_repeat_count = 0

        self.banner_x = SCREEN_WIDTH
        pyxel.init(SCREEN_WIDTH, SCREEN_HEIGHT, title="Chip8 Pyxelized", fps=FPS)
        self.reset_vm()
        #pyxel.image(0).load(0, 0, "assets/pyxel_logo_38x16.png")
        pyxel.load("chip8.pyxres")
        self.start()

    def start(self):
        # TODO: figure out sound resources and playing a sound effect.
        pyxel.sound(0)
        pyxel.run(self.update, self.draw)

    def reg(self):
        print("v0-vf -> " + str(self.V))

    def stop(self):
        pass

    def update(self):
        if pyxel.btnp(pyxel.KEY_RETURN):
            self.reset_vm()

        # Since the update frequency isn't high enough, we now do N ticks per update.
        for _ in range(TICKS_PER_UPDATE):
            self.tick()

        if self.sound > 0:
            pyxel.play(0, 0)

        # This should run at around 60hz me thinks.
        if self.delay > 0:
            self.delay -=1

        if self.sound > 0:
            self.sound -=1

        self.banner_x -=0.2
        if self.banner_x < -200:
            self.banner_x = SCREEN_WIDTH
    def draw(self):
        pyxel.rectb(CHIP8_X_OFFSET-2, CHIP8_Y_OFFSET-2, 68, 36, 11)
        pyxel.rect(0, 85, SCREEN_WIDTH, SCREEN_HEIGHT, 0)

        # for i, c in enumerate(BANNER_MSG):
        #     char_offset = i + 1
        #     pyxel.text(self.banner_x + (char_offset * 4),
        #         SCREEN_HEIGHT-8 + math.sin(pyxel.frame_count % char_offset/50) * 1.4, c,
        #         int((math.sin(pyxel.frame_count/100) * 20)) % 16)

        pyxel.text(2, 88, "ball Y (v7)=" + str(self.V[0x7]), 7)
        #pyxel.text(self.banner_x+1, SCREEN_HEIGHT-8, "Chip 8 - Pyxelized - by deckarep - 2022", 0)
        # TODO: if cls or draw OP occured, we know to blit the video ram to the screen.
        # Currently, we're drawing to the screen directly, but we should be blitting once and awhile only if needed.
        
        # TODO: if we want to show rendered text, we need to fix the problem above.
        #for x in range(0xF):
        #    pyxel.text(5, 38 + (x * 8), "v" + str(x) + "=" + hex(self.V[x]), 7)
        
        #for (m, x) in enumerate(self.data["foo"]):
        #    pyxel.text(20, 41 + (m * 15), x, pyxel.frame_count % 16)
        #pdb.set_trace()
        #pyxel.cls(0)
        #for i in range(100):
        #    pyxel.pset(random.randint(0,160), random.randint(0,120), random.randint(0,15))
        #pyxel.text(55, 41, "Hello, Pyxel!", pyxel.frame_count % 16)
        #pyxel.blt(61, 66, 0, 0, 0, 38, 16)

    # Resets the entire Chip8 VM state.
    def reset_vm(self):
        # program counter to the current instruction in memory. (12 bits addressable)
        self.PC = ROM_STARTING_ADDRESS
        # 16-bit register to point to locations in mem. (12 bits addressable)
        self.I = 0
        self.stack = []
        # 8-bit delay timer.
        self.delay = 0
        # 8-bit sound timer.
        self.sound = 0

        # Keypad state an array of 8-bit vals.
        self.keypad = [0] * 16

        # 16 8-bit general purpose registers. (V0-VF where VF is a flag register)
        self.V = [0] * 16
        
        # 4kb (4096 bytes to be exact), memory must be writable.
        # Load ROM's (which can self modify technically) into address 0x200.
        self.memory = [0] * VM_MEMORY_SIZE

        self.install_fonts()
        #self.load_rom("roms/IBM Logo.ch8")
        #self.load_rom("roms/bc_test.ch8") #Passing
        self.load_rom("roms/brix.rom")

        pyxel.cls(SCREEN_COLOR_OFF)

    def install_fonts(self):
        for i, b in enumerate(FONT_DATA):
            self.memory[FONT_STARTING_ADDRESS + i] = b
    
    # Loads a rom from disk into memory at the appropriate offset.
    def load_rom(self, rom_file):
        with io.open(rom_file, 'rb') as f:
            rom_data = f.read()
            for i, b in enumerate(rom_data):
                self.memory[ROM_STARTING_ADDRESS + i] = b

    # Performs one cycle.
    def tick(self):
        self.scan_keys()
        inst = self.fetch()
        self.decode_and_execute(inst)
        self.check_stalled()

    def scan_keys(self):
        for i, k in enumerate(KEYS_OF_INTEREST):
            # record button pressed key states
            if pyxel.btnp(k):
                self.keypad[i] = 1
            # record button released key states
            if pyxel.btnr(k):
                self.keypad[i] = 0

    def check_stalled(self):
        if self.opcode_repeat_count > MAX_STALLED_VM_CYCLES:
            self.opcode_repeat_count = 0
            self.last_opcode = 0
            self.reset_vm()

        if self.PC == self.last_opcode:
            self.opcode_repeat_count +=1
        else:
            self.opcode_repeat_count = 0
        self.last_opcode = self.PC

    def fetch(self):
        inst_16_bit = self.memory[self.PC] << 8 | self.memory[self.PC+1]
        self.PC = self.PC + 2
        return inst_16_bit

    def push(self, val):
        self.stack.append(val)

    def pop(self):
        result = self.stack.pop()
        assert (result is not None), "oh no! we popped a None!"
        return result

    def decode_and_execute(self, inst):
        inst_category = inst & 0xF000
        if inst_category == 0x0000:
            if inst == 0x00E0:
                # clear screen
                #print("inst: clear screen")
                pyxel.cls(SCREEN_COLOR_OFF)
            elif inst == 0x00EE:
                #print("inst: return from sub")
                self.PC = self.pop()
        elif inst_category == 0x1000:
            ##print("inst: jump")
            self.PC = inst & 0x0FFF
        elif inst_category == 0x2000:
            #print("inst: call subroutine")
            self.push(self.PC)
            self.PC = inst & 0xFFF
        elif inst_category == 0x3000:
            vx = (inst & 0x0F00) >> 8
            if self.V[vx] == inst & 0x0FF:
                #print("inst: if VX == NN skip 1 instruction")
                self.PC = self.PC + 2
        elif inst_category == 0x4000:
            vx = (inst & 0x0F00) >> 8
            if self.V[vx] != inst & 0x0FF:
                #print("inst: if VX != NN skip 1 instruction")
                self.PC = self.PC + 2
        elif inst_category == 0x5000:
            vx = (inst & 0x0F00) >> 8
            vy = (inst & 0x00F0) >> 4
            if self.V[vx] == self.V[vy]:
                #print("inst: if VX == VY skip 1 instruction")
                self.PC = self.PC + 2
        elif inst_category == 0x6000:
            vx = (inst & 0x0F00) >> 8
            self.V[vx] = inst & 0x00FF
            #print("inst: set register VX to the value NN")
        elif inst_category == 0x7000:
            vx = (inst & 0x0F00) >> 8
            #print("inst: add value to register VX")
            self.V[vx] = (self.V[vx] + inst) & 0x00FF
        elif inst_category == 0x8000:
            #print("inst: set/or/and/xor/add arithmetic")
            inst_subcategory = inst & 0x000F
            if inst_subcategory == 0:
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4
                self.V[vx] = self.V[vy]
            elif inst_subcategory == 1:
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4
                self.V[vx] = self.V[vx] | self.V[vy]
            elif inst_subcategory == 2:
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4
                self.V[vx] = self.V[vx] & self.V[vy]
            elif inst_subcategory == 3:
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4
                self.V[vx] = self.V[vx] ^ self.V[vy]
            elif inst_subcategory == 4:
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4

                total = self.V[vx] + self.V[vy]

                if total > 255:
                    self.V[0xF] = 1
                else:
                    self.V[0xF] = 0
                self.V[vx] = total & 0xFF
            elif inst_subcategory == 5:
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4
                
                if self.V[vx] > self.V[vy]:
                    self.V[0xF] = 1
                else:
                    self.V[0xF] = 0

                # In Python must handle simulate byte-sized math to prevent negative numbers.
                if self.V[0xF] == 0:
                    negNum = self.V[vx] - self.V[vy]
                    self.V[vx] = 256 - abs(negNum)
                else:
                    # Business as usual.
                    self.V[vx] = self.V[vx] - self.V[vy]
            elif inst_subcategory == 6:
                #print("inst: shift right - ambiguous")
                #pdb.set_trace()
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4
                
                # set flag to bit of whatever got lopped off the RIGHT least sig bit end: 0 or 1.
                self.V[0xF] = self.V[vx] & 0x1

                # now do the RIGHT shift.
                self.V[vx] = self.V[vx] >> 1
            elif inst_subcategory == 7:
                #pdb.set_trace()
                vx = (inst & 0x0F00) >> 8
                vy = (inst & 0x00F0) >> 4
                
                if self.V[vy] > self.V[vx]:
                    self.V[0xF] = 1
                else:
                    self.V[0xF] = 0

                num = self.V[vy] - self.V[vx]

                # In Python must handle simulate byte-sized math to prevent negative numbers.
                if self.V[0xF] == 0:
                    num = 256 - abs(num)

                self.V[vx] = num
            elif inst_subcategory == 0xE:
                #print("inst: shift left - ambiguous")
                vx = (inst & 0x0F00) >> 8
                # vy = (inst & 0x00F0) >> 4 (vy is ignored here)
                
                # set flag to bit of whatever got lopped off the LEFT end most sig bit: 0 or 1.
                self.V[0xF] = (self.V[vx] & 0x80) >> 7

                # now do the RIGHT shift.
                self.V[vx] = self.V[vx] << 1
                
        elif inst_category == 0x9000:
            vx = (inst & 0x0F00) >> 8
            vy = (inst & 0x00F0) >> 4
            if self.V[vx] != self.V[vy]:
                #print("inst: if VX != VY skip 1 instruction")
                self.PC = self.PC + 2
        elif inst_category == 0xA000:
            self.I = inst & 0x0FFF
            #print("inst: set register I to the value NNN")
        elif inst_category == 0xB000:
            #print("inst: jump to offset: ambiguous instruction utilizing primary implementation")
            self.PC = self.V[0x0] + (inst & 0x0FFF)
        elif inst_category == 0xC000:
            #print("inst: random")
            vx = (inst & 0xF00) >> 8
            self.V[vx] = random.randint(0, 255) & (inst & 0x0FF)
        elif inst_category == 0xD000:
            #print("inst: display/draw")
            vx = (inst & 0xF00) >> 8
            vy = (inst & 0xF0) >> 4
            height = (inst & 0xF)

            # Modulus ensures we handle "wrap-around" drawing.
            xPos = (self.V[vx] % CHIP8_WIDTH) + CHIP8_X_OFFSET
            yPos = (self.V[vy] % CHIP8_HEIGHT) + CHIP8_Y_OFFSET
            self.V[0xF] = 0
            
            for row in range(height):
                spriteByte = self.memory[self.I + row]
                for col in range(8):
                    spritePix = spriteByte & (0x80 >> col)
                    screenPix = pyxel.pget(xPos + col, yPos + row)

                    if spritePix:
                        if screenPix == SCREEN_COLOR_ON:
                            self.V[0xF] = 1
                        # Simulate XOR logic with this crap (since we don't have access to raw pixel data)
                        currentScreenPixel = pyxel.pget(xPos + col, yPos + row)
                        if currentScreenPixel == SCREEN_COLOR_ON:
                            pyxel.pset(xPos + col, yPos + row, SCREEN_COLOR_OFF)
                        else:
                            pyxel.pset(xPos + col, yPos + row, SCREEN_COLOR_ON)
        elif inst_category == 0xE000:
            inst_subcategory = inst & 0xFF
            if inst_subcategory == 0x9E:
                vx = (inst & 0x0F00) >> 8
                key = self.V[vx]
                if (self.keypad[key]):
                    self.PC += 2
            elif inst_subcategory == 0xA1:
                vx = (inst & 0x0F00) >> 8
                key = self.V[vx]
                if (not self.keypad[key]):
                    self.PC += 2
        elif inst_category == 0xF000:
            inst_subcategory = inst & 0x00FF
            if inst_subcategory == 0x07:
                vx = (inst & 0x0F00) >> 8
                self.V[vx] = self.delay
            elif inst_subcategory == 0x15:
                vx = (inst & 0x0F00) >> 8
                self.delay = self.V[vx]
            elif inst_subcategory == 0x18:
                vx = (inst & 0x0F00) >> 8
                self.sound = self.V[vx]
            elif inst_subcategory == 0x29:
                vx = (inst & 0x0F00) >> 8
                self.I = FONT_STARTING_ADDRESS + (FONT_BYTE_SIZE * self.V[vx]) # font size is 5 chars each.
            elif inst_subcategory == 0x0A:
                #pdb.set_trace()
                vx = (inst & 0x0F00) >> 8
                if self.keypad[0]:
                    self.V[vx] = 0
                elif self.keypad[1]:
                    self.V[vx] = 1
                elif self.keypad[2]:
                    self.V[vx] = 2
                elif self.keypad[3]:
                    self.V[vx] = 3
                elif self.keypad[4]:
                    self.V[vx] = 4
                elif self.keypad[5]:
                    self.V[vx] = 5
                elif self.keypad[6]:
                    self.V[vx] = 6
                elif self.keypad[7]:
                    self.V[vx] = 7
                elif self.keypad[8]:
                    self.V[vx] = 8
                elif self.keypad[9]:
                    self.V[vx] = 9
                elif self.keypad[10]:
                    self.V[vx] = 10
                elif self.keypad[11]:
                    self.V[vx] = 11
                elif self.keypad[12]:
                    self.V[vx] = 12
                elif self.keypad[13]:
                    self.V[vx] = 13
                elif self.keypad[14]:
                    self.V[vx] = 14
                elif self.keypad[15]:
                    self.V[vx] = 15
                else:
                    self.PC -= 2
            elif inst_subcategory == 0x1E:
                vx = (inst & 0x0F00) >> 8
                self.I += self.V[vx]
            elif inst_subcategory == 0x33:
                # BCD
                vx = (inst & 0x0F00) >> 8
                val = self.V[vx]

                # ones place
                self.memory[self.I + 2] = val % 10
                val = val // 10

                # tens place
                self.memory[self.I + 1] = val % 10
                val = val // 10

                # hundreds place
                self.memory[self.I] = val % 10
            elif inst_subcategory == 0x55:
                vx = (inst & 0x0F00) >> 8
                for n in range(vx + 1):
                    self.memory[self.I + n] = self.V[n]
            elif inst_subcategory == 0x65:
                vx = (inst & 0x0F00) >> 8
                for n in range(vx + 1):
                    self.V[n] = self.memory[self.I + n]
            else:
                print("inst subcategory: not implemented (" + hex(inst) + ")")
        else:
            print("instruction not handled (" + hex(inst) + ")")

def main():
    Chip8VM()

# Special bootstrapping for pyxel applications hence the: <run_path>
if __name__ == '<run_path>':
    main()
