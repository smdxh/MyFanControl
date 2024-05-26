import time
import clr
import sys
import serial
import os
from serial.serialutil import SerialException,SerialTimeoutException
import serial.tools.list_ports
from tkinter import messagebox
import configparser
projectPath = os.path.dirname(os.path.abspath(__file__))
sys.path.append(projectPath) #dll路径加入系统环境
clr.AddReference('OpenHardwareMonitorLib')
from OpenHardwareMonitor.Hardware import Computer # type: ignore

conf = configparser.ConfigParser()
conf.read('config.ini')
def saveConfig(section, option, value=None):
    conf.set(section,option,str(value))
    with open('config.ini','w') as configfile:
        conf.write(configfile)


def iniConfig():
    conf['serial'] = {
        'baudrate' : 9600,          # 波特率  
        'bytesize' : serial.EIGHTBITS,  # 数据位长度为8位  
        'parity' : serial.PARITY_NONE,   # 无奇偶校验  
        'stopbits' : serial.STOPBITS_ONE,  # 1位停止位  
        'timeout' : 1,             # 读取超时时间为1秒
        'write_timeout' : 1,       # 写超时
    }
    conf['DEFAULT'] = {
        'rightResult' : "DOWN", #PWM设备正确执行时应该返回的信息
    }
    conf['USER'] = {
        'TIMEOUT_EXCEPTION' : 2, 
        'RETURN_ERROR' : 2, 
        'manual' : 0, 
        'begin_temperature' : 20,
        'max_temperature' : 80,

    }

    with open('config.ini','w') as configfile:
        conf.write(configfile)
if "serial" not in conf:
    iniConfig()

c = Computer()
c.CPUEnabled = True
c.GPUEnabled = True
c.Open()
cpu = c.Hardware[0]
gpu = c.Hardware[1]

ser = serial.Serial()  # 创建串口连接对象  
ser.baudrate = conf['serial']['baudrate']  # 波特率  
ser.bytesize = int(conf['serial']['bytesize'])  # 数据位长度为8位  
ser.parity = conf['serial']['parity']   # 无奇偶校验  
ser.stopbits = conf.getint('serial','stopbits')  # 1位停止位  
ser.timeout = int(conf['serial']['timeout'])  # 读取超时时间为1秒
ser.write_timeout = conf.getint('serial','write_timeout')  # 写超时

errCount = 0
oldDR = -100 #必须大于波动幅度差值，否则启动时不发送设置信号
rightResult = conf['DEFAULT']['rightResult'].encode() #PWM设备正确执行时应该返回的信息

class PWMResponse:
    NONE = -1
    SUCCESS = 0
    RETURN_ERROR = 4
    UNKNOW_EXCEPTION = 3
    SERIAL_EXCEPTION = 2
    TIMEOUT_EXCEPTION = 1

    def __init__(self,code:int,description:str,dutyRatio,response=None):
        self.code = code
        self.description = description # 弹窗提示
        self.response = response # ttl返回的内容
        self.dutyRatio = dutyRatio #占空比


"""
获取风扇控制器端口名
t:获取端口失败时的重试次数
"""
def getFanPort(t):
    for a in range(t): #尝试寻找目标串口
        ports = serial.tools.list_ports.comports()
        if len(ports) > 0: #发现串口列表
            for i in ports:
                i = list(i)
                if "CH340" in i[1]: #发现目标串口
                    print('COM描述：',i[1],"名称",i[0])
                    return i[0]
        ser.close() # 出问题需要立刻关闭端口，以便重新获取端口号
        time.sleep(1)
    return None

"""
获取CPU温度
"""
def getCPUTemp():
    cpu.Update()
    cpuTem = 0.0
    for a in range(0,len(cpu.Sensors)):
        # print(cpu.Sensors[a].Identifier,cpu.Sensors[a].get_Value())
        if "/temperature" in str(cpu.Sensors[a].Identifier):
            newTem = cpu.Sensors[a].get_Value()
            if newTem is not None:
                if cpuTem < newTem: cpuTem = newTem
    # print('cpu temperature',cpuTem)
    return round(cpuTem)
"""
获取GPU温度
"""
def getGPUTemp():
    gpu.Update()
    gpuTem = gpu.Sensors[0].get_Value()
    # print('gpu temperature',gpuTem)
    return round(gpuTem)
"""
设置风扇的占空比
DR:占空比(Duty Ratio)，支持0-100间的整数
"""
def setPWM(DR):
    global errCount,oldDR
    ttlresult = b''
    DR = round(DR)
    if DR <0:DR =0
    if DR >100: DR = 100
    if abs(DR-oldDR) <= 2 :return PWMResponse(PWMResponse.NONE,('%02d' %DR),('%02d' %DR),"无变化")#波动幅度小，不进行占空比调整
    try:
        if not ser.is_open: #检查串口是否开启（出错时关闭）
            ser.port = getFanPort(3) #尝试获取CH340的串口号，尝试3次，每次1秒
            ser.open()
        print('PWM Duty cycle dU1:%03d' %DR)
        # ser.write(b'DOWN')
        ser.write(b'dU1:%03d' %DR)
        oldDR = DR
        ttlresult = ser.readline()
    except SerialTimeoutException:
        ser.close() # 出问题需要立刻关闭端口，以便重新获取端口号
        return PWMResponse(PWMResponse.TIMEOUT_EXCEPTION,'读写超时，你PWM和ttl接口是不是生锈了',('%02d' %DR))
    except SerialException:
        ser.close() # 出问题需要立刻关闭端口，以便重新获取端口号
        return PWMResponse(PWMResponse.SERIAL_EXCEPTION,'没找到USB设备',('%02d' %DR))
    except Exception as r:
        ser.close() # 出问题需要立刻关闭端口，以便重新获取端口号
        return PWMResponse(PWMResponse.UNKNOW_EXCEPTION,'不知道发生什么了，这是报错'+str(r)+'要不要再救一下？',('%02d' %DR))
    if ttlresult == rightResult:  #PWM返回正确信号，计数器清零
        errCount = 0
    else: #PWM返回一个错误信号
        errCount += 1
        # print('PWM第%d次返回错误信号%s' %(errCount,result.decode('utf-8')))
        ser.close() # 出问题需要立刻关闭端口，以便重新获取端口号
    if errCount > 2: #PWM返回错误信号过多提交用户判断
        return PWMResponse(PWMResponse.RETURN_ERROR,'PWM返回错误信号次数过多',('%02d' %DR),ttlresult.decode('utf-8'))
    return PWMResponse(PWMResponse.SUCCESS,('%02d' %DR),('%02d' %DR),ttlresult.decode('utf-8'))



# 成功运行时写入运行时间
# fileText = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
# with open('启动时间.txt','w') as f:
#     f.write(fileText)