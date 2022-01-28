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
        self.setup_dfa_dispatch()
        self.reset_vm()
        #pyxel.image(0).load(0, 0, "assets/pyxel_logo_38x16.png")
        pyxel.load("chip8.pyxres")
        self.start()

    def start(self):
        # TODO: figure out sound resources and playing a sound effect.
        pyxel.sound(0)
        pyxel.run(self.update, self.draw)

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

    def setup_dfa_dispatch(self):
        self.inst_dfa_tree = {
            '0' : {
                '0' : {
                    'E': {
                        '0': self.op_cls,
                        'E': self.op_return
                    }
                }
            },
            '1' : {
                'N' : {
                    'N': {
                        'N': self.op_jump
                    }
                }
            },
            '2' : {
                'N' : {
                    'N': {
                        'N': self.op_call
                    }
                }
            },
            '3' : {
                'X': {
                    'N': {
                        'N': self.op_skip_eq
                    }
                }
            },
            '4' : {
                'X': {
                    'N': {
                        'N': self.op_skip_not_eq
                    }
                }
            },
            '5' : {
                'X': {
                    'Y': {
                        '0': self.op_skip_eq_vy
                    }
                }
            },
            '6' : {
                'X': {
                    'N': {
                        'N': self.op_set_vx
                    }
                }
            },
            '7' : {
                'X': {
                    'N': {
                        'N': self.op_add_vx
                    }
                }
            },
            '8' : {
                'X': {
                    'Y': {
                        '0': self.op_8XY0,
                        '1': self.op_8XY1,
                        '2': self.op_8XY2,
                        '3': self.op_8XY3,
                        '4': self.op_8XY4,
                        '5': self.op_8XY5,
                        '6': self.op_8XY6,
                        '7': self.op_8XY7,
                        'E': self.op_8XYE,

                    }
                }
            },
            '9' : {
                'X': {
                    'Y': {
                        '0': self.op_9XY0
                    }
                }
            },
            'A' : {
                'N': {
                    'N': {
                        'N': self.op_ANNN
                    }
                }
            },
            'B' : {
                'N': {
                    'N': {
                        'N': self.op_BNNN
                    }
                }
            },
            'C' : {
                'X': {
                    'N': {
                        'N': self.op_CXNN
                    }
                }
            },
            'D' : {
                'X': {
                    'Y': {
                        'N': self.op_draw
                    }
                }
            },
            'E' : {
                'X': {
                    '9': {
                        'E': self.op_EX9E
                    },
                    'A': {
                        '1': self.op_EXA1
                    }
                }
            },
            'F' : {
                'X': {
                    '0': {
                        '7': self.op_FX07,
                        'A': self.op_FX0A
                    },
                    '1': {
                        '5': self.op_FX15,
                        '8': self.op_FX18,
                        'E': self.op_FX1E
                    },
                    '2': {
                        '9': self.op_FX29
                    },
                    '3': {
                        '3': self.op_FX33
                    },
                    '5': {
                        '5': self.op_FX55
                    },
                    '6': {
                        '5': self.op_FX65
                    }
                }
            },
        }

    def decode_and_execute(self, inst):
        inst_category = inst & 0xF000

        inst_hex = "{:04x}".format(inst).upper()
        nxt = self.inst_dfa_tree.get(inst_hex[0])
        assert nxt is not None, "instruction was not handled: " + inst_hex

        nesting = 1
        while True:
            # We found our op to dispatch.
            if nesting == 4:
                nxt(inst)
                # if we got here instruction should have been handled so return.
                return
            if 'N' in nxt:
                #print('n found')
                nxt = nxt['N']
            elif 'X' in nxt:
                #print('x found')
                nxt = nxt['X']
            elif 'Y' in nxt:
                #print('y found')
                nxt = nxt['Y']
            elif inst_hex[nesting] in nxt:
                #print('literal found')
                nxt = nxt[inst_hex[nesting]]
            nesting +=1

    def op_nop(self, inst):
        pass

    def op_cls(self, inst):
        pyxel.cls(SCREEN_COLOR_OFF)

    def op_jump(self, inst):
        self.PC = inst & 0x0FFF

    def op_return(self, inst):
        self.PC = self.pop()

    def op_call(self, inst):
        self.push(self.PC)
        self.PC = inst & 0xFFF

    def op_draw(self, inst):
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

    def op_skip_eq(self, inst):
        vx = (inst & 0x0F00) >> 8
        if self.V[vx] == inst & 0x0FF:
            #print("inst: if VX == NN skip 1 instruction")
            self.PC = self.PC + 2

    def op_skip_not_eq(self, inst):
        vx = (inst & 0x0F00) >> 8
        if self.V[vx] != inst & 0x0FF:
            #print("inst: if VX != NN skip 1 instruction")
            self.PC = self.PC + 2

    def op_skip_eq_vy(self, inst):
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4
        if self.V[vx] == self.V[vy]:
            #print("inst: if VX == VY skip 1 instruction")
            self.PC = self.PC + 2

    def op_set_vx(self, inst):
        vx = (inst & 0x0F00) >> 8
        self.V[vx] = inst & 0x00FF
        #print("inst: set register VX to the value NN")

    def op_add_vx(self, inst):
        vx = (inst & 0x0F00) >> 8
        #print("inst: add value to register VX")
        self.V[vx] = (self.V[vx] + inst) & 0x00FF

    def op_8XY0(self, inst):
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4
        self.V[vx] = self.V[vy]

    def op_8XY1(self, inst):
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4
        self.V[vx] = self.V[vx] | self.V[vy]

    def op_8XY2(self, inst):
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4
        self.V[vx] = self.V[vx] & self.V[vy]

    def op_8XY3(self, inst):
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4
        self.V[vx] = self.V[vx] ^ self.V[vy]

    def op_8XY4(self, inst):
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4

        total = self.V[vx] + self.V[vy]

        if total > 255:
            self.V[0xF] = 1
        else:
            self.V[0xF] = 0
        self.V[vx] = total & 0xFF

    def op_8XY5(self, inst):
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

    def op_8XY6(self, inst):
        #print("inst: shift right - ambiguous")
        #pdb.set_trace()
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4

        # set flag to bit of whatever got lopped off the RIGHT least sig bit end: 0 or 1.
        self.V[0xF] = self.V[vx] & 0x1

        # now do the RIGHT shift.
        self.V[vx] = self.V[vx] >> 1

    def op_8XY7(self, inst):
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

    def op_8XYE(self, inst):
        #print("inst: shift left - ambiguous")
        vx = (inst & 0x0F00) >> 8
        # vy = (inst & 0x00F0) >> 4 (vy is ignored here)

        # set flag to bit of whatever got lopped off the LEFT end most sig bit: 0 or 1.
        self.V[0xF] = (self.V[vx] & 0x80) >> 7

        # now do the RIGHT shift.
        self.V[vx] = self.V[vx] << 1

    def op_9XY0(self, inst):
        vx = (inst & 0x0F00) >> 8
        vy = (inst & 0x00F0) >> 4
        if self.V[vx] != self.V[vy]:
            #print("inst: if VX != VY skip 1 instruction")
            self.PC = self.PC + 2

    def op_ANNN(self, inst):
        self.I = inst & 0x0FFF
        #print("inst: set register I to the value NNN")

    def op_BNNN(self, inst):
        #print("inst: jump to offset: ambiguous instruction utilizing primary implementation")
        self.PC = self.V[0x0] + (inst & 0x0FFF)

    def op_CXNN(self, inst):
        #print("inst: random")
        vx = (inst & 0xF00) >> 8
        self.V[vx] = random.randint(0, 255) & (inst & 0x0FF)

    def op_EX9E(self, inst):
        vx = (inst & 0x0F00) >> 8
        key = self.V[vx]
        if (self.keypad[key]):
            self.PC += 2

    def op_EXA1(self, inst):
        vx = (inst & 0x0F00) >> 8
        key = self.V[vx]
        if (not self.keypad[key]):
            self.PC += 2

    def op_FX07(self, inst):
        vx = (inst & 0x0F00) >> 8
        self.V[vx] = self.delay

    def op_FX0A(self, inst):
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

    def op_FX15(self, inst):
        vx = (inst & 0x0F00) >> 8
        self.delay = self.V[vx]

    def op_FX18(self, inst):
        vx = (inst & 0x0F00) >> 8
        self.sound = self.V[vx]

    def op_FX1E(self, inst):
        vx = (inst & 0x0F00) >> 8
        self.I += self.V[vx]

    def op_FX29(self, inst):
        vx = (inst & 0x0F00) >> 8
        self.I = FONT_STARTING_ADDRESS + (FONT_BYTE_SIZE * self.V[vx]) # font size is 5 chars each.

    def op_FX33(self, inst):
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

    def op_FX55(self, inst):
        vx = (inst & 0x0F00) >> 8
        for n in range(vx + 1):
            self.memory[self.I + n] = self.V[n]

    def op_FX65(self, inst):
        vx = (inst & 0x0F00) >> 8
        for n in range(vx + 1):
            self.V[n] = self.memory[self.I + n]

def main():
    Chip8VM()

# Special bootstrapping for pyxel applications hence the: <run_path>
if __name__ == '<run_path>':
    main()
