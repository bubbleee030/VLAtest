from pyModbusTCP.client import ModbusClient
import time
# import yaml
import os
import threading

def closeRobot(c):
    c.open()
    c.write_multiple_registers((0x1001), int2DRA(4))
    c.close()
    print("stop DRA!")
    
    
def connectRobot(SERVER_HOST = "192.168.1.232",SERVER_PORT = 502,unit_id=2):

    c = ModbusClient(host=SERVER_HOST, port=SERVER_PORT, unit_id=unit_id, auto_open=True)

    return c

def getRobotP(c):

    c.open()
    #regs = c.read_holding_registers(0x1001,2)
    #print("get p:",regs)
    c.write_multiple_registers(0x1001, int2DRA(1))
    # time.sleep(1)
    #c.close()
    #time.sleep(1)

    for i in range(10):
        print("wait for read",i)
        regs = c.read_holding_registers(0x1001,1)
        time.sleep(1)
        try:
            if regs[0]==0:
                break
        except:
            c.close()
            c.open()

    try:
        #c.open()
        regs = c.read_holding_registers(0x1100,12)
        pos=[]
        x=int(len(regs)/2)
        for i in range(x):
            a=regs[(2*i)]
            b=regs[(2*i)+1]
            tmp=DRA2intL(a,b)/1000
            #print(a,b,tmp)
            pos.append(tmp)
        c.write_multiple_registers(0x1001, int2DRA(0))
        c.write_multiple_registers(0x1002, int2DRA(0))
        c.close()
    except:
        c.close()
        c.open()
        regs = c.read_holding_registers(0x1100,12)
        #print(regs)
        pos=[]
        x=int(len(regs)/2)
        for i in range(x):
            a=regs[(2*i)]
            b=regs[(2*i)+1]
            tmp=DRA2intL(a,b)/1000
            #print(a,b,tmp)
            pos.append(tmp)
        c.write_multiple_registers(0x1001, int2DRA(0))
        c.write_multiple_registers(0x1002, int2DRA(0))
        c.close
    return pos

def DRA2int(i):
    if(i>32767):
        return i-65536
    else:
        return i
    
def DRA2intL(a1,b1):
    out=bin(b1)
    if(len(out)<18):
        out="0b"+out[2::].zfill(16)
    out2=bin(a1)
    out2=out2[2::]
    if(len(out2)<16):
        out2=out2.zfill(16)
    f=out+out2
    if(f[2]=='1'):
        f=int(f[3::],2)-2147483648
        return f
    f=int(f,2)
    
    return f


def intL2DRA(i):
    if(i<0):
        f=i+4294967296
        f=bin(f)
        b=int(f[0:18],2)
        a=int(f[18::],2)
        return [a,b]
    else:
        if(i<65536):
            b=0
            a=i
            return [a,b]
        else:
            f=bin(i)      
            a=int(f[-16::],2)
            b=int(f[0:-16],2)
            return [a,b]
        
def int2DRA(i):
    if(i<0):
        return [i+65536]
    elif(i<32767):
        return [i]
    else:
        print("out of 32767!")
        return [0]
        
def reset_alarm(c):
    c.write_multiple_registers((0x0026), int2DRA(1)) # J1: 0h001 => int:1
    c.write_multiple_registers((0x0026), int2DRA(256)) # J2: 0h100 => int:256
    c.write_multiple_registers((0x0027), int2DRA(1)) # J3: 0h1 => int:1
    c.write_multiple_registers((0x0027), int2DRA(256)) # J4: 0h100 => int:256
    c.write_multiple_registers((0x0020), int2DRA(1)) # J5: 0h1 => int:1
    c.write_multiple_registers((0x0020), int2DRA(256)) # J6: 0h100 => int:256
    print("Alarm reset success")

def move(ip_choice="192.168.1.232"):
    
    try:
        print("Connecting to Modbus server at 192.168.1.232:502...")
        # drv70L
        c = connectRobot(SERVER_HOST = ip_choice,SERVER_PORT = 502,unit_id=2)
        c.timeout = 0.5
        if not c.open():
            print("ERROR: Failed to connect to robot controller.")
            print("Please check:")
            print("  1. Robot controller is powered on")
            print("  2. Network cable is connected")
            print("  3. IP address 192.168.1.232 is reachable")
            exit(1)
        print("Connection successful!")
        reset_alarm(c)
        # Servo on
        c.write_single_register(0x0010,1) # All joints on(1)/off(2)
        regs2 = c.read_holding_registers(0x0010, 1)
#         print( DRA2int(regs2[0]))
        print("All servo ON")
        time.sleep(2)

        # servo go home
        print("Initializing...")
        c.write_single_register(0x0300,1405)
        regs2 = c.read_holding_registers(0x0300, 1)
        print( DRA2int(regs2[0]))
        print("Go home completed")

        print("System sleep 20 sec")
        time.sleep(20)        
        
        #============ read modbus=================
        #讀取範例為W(16bit int)
        modbus = 0x1001
        #太久沒讀取modbus的話python會自動斷線，最好是直接讀兩次
        regs = c.read_holding_registers(modbus, 1)
        regs = c.read_holding_registers(modbus, 1)
        if regs is None:
            print("ERROR: Failed to read Modbus registers")
            c.close()
            exit(1)

        regs = c.read_holding_registers(modbus, 1)
        print(f"modbus {hex(modbus)}={DRA2int(regs[0])}")        
        
        
        
        #================ write modbus =============
        
        end_modbus = 0x0330
        # max axis: x[671665~-43264]
        #           y[469456~-469446]
        #           z[968425~155572] 注意若前面有加裝其他工具需更改
        #           rx[89999~-89999]
        #           ry[89999~-89999]
        #           rz[179999~68269, -68269~-89999]
        # home = [444000,0,744000,0,-89999,179999]

        pos_tmp=[644000,269456,344000,0,-89999,179999] #modbus只有int，用pos資料比較大，用6個DW去存
        #用DW去存(16bit*2)
        for i in range(6):
            c.write_multiple_registers((end_modbus+2*i), intL2DRA(pos_tmp[i]))
        print("Write complete")

        # change mode(0:world, 1:user, 2:tool, 3:joint)
        c.write_single_register(0x033E,3)
        regs2 = c.read_holding_registers(0x033E, 1)
        print( DRA2int(regs2[0]))

        # change speed(unit: %)
        c.write_single_register(0x0324,80)
        regs2 = c.read_holding_registers(0x324, 1)
        print( DRA2int(regs2[0]))

        # servo p2p
        c.write_single_register(0x0300,301)
        regs2 = c.read_holding_registers(0x0300, 1)
        print( DRA2int(regs2[0]))

        print("System sleep 20 sec")
        time.sleep(20)

        # servo go home
        c.write_single_register(0x0300,1405)
        regs2 = c.read_holding_registers(0x0300, 1)
        print( DRA2int(regs2[0]))
        print("Go home completed")

        print("System sleep 20 sec")
        time.sleep(20)

        # Servo off
        c.write_single_register(0x0010,2) # All joints on(1)/off(2)
        regs2 = c.read_holding_registers(0x0010, 1)
        print( DRA2int(regs2[0]))

        # Close DRA
        c.close()
        print(f"DRV {ip_choice} closed")


        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        print("Please ensure robot controller is accessible at 192.168.1.232")
        exit(1)

if __name__ == "__main__":
    print("=== 232 start ===")
    move("192.168.1.232")
    time.sleep(2)
    print("=== 232 completed ===")

    print("=== 233 start ===")
    move("192.168.1.233")
    time.sleep(2)
    print("=== 233 completed ===")

        