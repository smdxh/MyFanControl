from controlTool import *
import sys
from PyQt6.QtCore import QCoreApplication,QTimer,Qt,QThread,pyqtSignal
from PyQt6.QtGui import QIcon,QAction
from PyQt6.QtWidgets import QApplication,QMainWindow,QSystemTrayIcon,QMenu
from PyQt6.QtWidgets import QLabel,QGridLayout,QWidget,QCheckBox,QMessageBox,QSlider
from PIL import Image, ImageDraw
TITLE = "机箱风扇控制器2.1"

class setPWMThread(QThread):
    # 定义一个信号，用于向主线程发送数据
    data_sent = pyqtSignal(PWMResponse)

    def __init__(self, parent=None, data = None):
        super(setPWMThread, self).__init__(parent)
        self.data = data
 
    def __del__(self):
        self.wait()
 
    def run(self):
        result = setPWM(self.data)
        self.data_sent.emit(result)


class WinForm(QMainWindow):
    def __init__(self,parent=None):
        super(WinForm,self).__init__(parent)
        self.sysIcon = QIcon('fan.png')
        self.result = PWMResponse(PWMResponse.NONE,"0","0","无变化")
        self.isWait = False
        self.initWindow()
        self.initTrayIcon()
        self.initUI()

    # 初始化主界面UI
    def initUI(self):
        self.label1 = QLabel("CPU温度：获取中...")
        self.label2 = QLabel("GPU温度：获取中...")
        self.label3 = QLabel("占空比：获取中...")
        self.label4 = QLabel("返回结果：获取中...")
        self.label5 = QLabel("")

        self.cb1 = QCheckBox('读写超时提示',self)
        self.cb2 = QCheckBox('PWM返回错误信号提示',self)
        self.cb3 = QCheckBox('手动调整占空比',self)

        self.s = QSlider(Qt.Orientation.Horizontal)
        self.s.setMaximum(100)
        self.s.setMinimum(0)
        self.s.setPageStep(10)
        self.s.setSingleStep(1)
        self.s.setTickInterval(10) #刻度间隔
        self.s.setTickPosition(QSlider.TickPosition.TicksBelow) #在（水平）滑块下方绘制刻度线

        self.cb1.setChecked(conf.getint('USER','TIMEOUT_EXCEPTION'))
        self.cb2.setChecked(conf.getint('USER','RETURN_ERROR'))
        self.cb3.setChecked(conf.getint('USER','manual'))

        mylayout = QGridLayout()
        mylayout.addWidget(self.label1,0,0)
        mylayout.addWidget(self.label2,1,0)
        mylayout.addWidget(self.label3,2,0)
        mylayout.addWidget(self.label4,4,0)
        mylayout.addWidget(self.cb1,0,1)
        mylayout.addWidget(self.cb2,1,1)
        mylayout.addWidget(self.cb3,2,1)
        mylayout.addWidget(self.label5,4,1)
        mylayout.addWidget(self.s,3,0,1,2,alignment=Qt.AlignmentFlag.AlignVCenter)

        self.cb1.stateChanged.connect(self.changecb1)
        self.cb2.stateChanged.connect(self.changecb2)
        self.cb3.stateChanged.connect(self.changecb3)
        self.s.sliderPressed.connect(self.changes)
        self.s.sliderMoved.connect(self.changes)
        self.s.sliderPressed.connect(self.changes)

        self.setLayout(mylayout)
        #创建widget窗口实例
        main_frame=QWidget()
        #加载布局
        main_frame.setLayout(mylayout)
        #把widget窗口加载到主窗口的中央位置
        self.setCentralWidget(main_frame)
        self.mythread = setPWMThread(data="")
        self.timer = QTimer()
        self.timer.start(1000) #每1000ms刷新一次
        self.timer.timeout.connect(self.updateUI)
    # 勾选框变化
    def changecb1(self,a):
        conf.set('USER','TIMEOUT_EXCEPTION',str(a))
        with open('config.ini','w') as configfile:
            conf.write(configfile)
    # 勾选框变化
    def changecb2(self,a):
        conf.set('USER','RETURN_ERROR',str(a))
        with open('config.ini','w') as configfile:
            conf.write(configfile)
    # 勾选框变化
    def changecb3(self,a):
        conf.set('USER','manual',str(a))
        with open('config.ini','w') as configfile:
            conf.write(configfile)
    # 滑动条变化
    def changes(self):
        self.cb3.setChecked(Qt.CheckState.Checked.value)

    # 更新主界面内容
    def updateUI(self):
        gpuTem = getGPUTemp()
        cpuTem = getCPUTemp()
        maxTem = gpuTem
        if cpuTem > gpuTem : maxTem = cpuTem
        if self.cb3.isChecked():
            self.dutyRatio = self.s.value()
        else:
            self.dutyRatio = round((maxTem-20) * 1.6)
        self.label1.setText("CPU温度：%d" %cpuTem)
        self.label2.setText("GPU温度：%d" %gpuTem)
        if self.mythread.isRunning() :
            self.label4.setText("返回结果：%s" %"线程运行中")
        elif self.isWait == True:
            self.label4.setText("返回结果：%s" %"错误待处理")
        else:
            self.mythread = setPWMThread(data=self.dutyRatio) #设置风扇占空比
            self.mythread.data_sent.connect(self.on_data_received)
            self.mythread.start()
        

    def on_data_received(self,result):
        self.result = result
        self.label3.setText("占空比：%s" %result.dutyRatio)
        if not self.cb3.isChecked():
            self.s.setValue(self.dutyRatio)
        self.resultMessage(result)
        self.label4.setText("返回结果：%s" %result.response)

    #修改托盘图标
    def changeTrayIcon(self,result):
        image = Image.new("RGBA",(12,12))
        id = ImageDraw.Draw(im=image)
        id.text(xy=(0,0),text=result.dutyRatio,fill='#FFFFFF')
        self.trayIcon.setIcon(QIcon(image.toqpixmap()))

    # 对ttl返回的结果进行处理
    def resultMessage(self,result:PWMResponse):
        match result.code:
            case PWMResponse.NONE : return
            case PWMResponse.SUCCESS : 
                self.changeTrayIcon(result)
            case PWMResponse.TIMEOUT_EXCEPTION : 
                self.changeTrayIcon(result)
                if self.cb1.isChecked():
                    self.isWait = True
                    result = QMessageBox.question(self,TITLE,result.description,QMessageBox.StandardButton.Retry,QMessageBox.StandardButton.Cancel)
                    self.isWait = False
                    self.cb1.setChecked(result == QMessageBox.StandardButton.Retry)
            case PWMResponse.RETURN_ERROR : 
                self.changeTrayIcon(result)
                if self.cb2.isChecked():
                    self.isWait = True
                    result = QMessageBox.question(self,TITLE,result.description,QMessageBox.StandardButton.Retry,QMessageBox.StandardButton.Cancel)
                    self.isWait = False
                    self.cb2.setChecked(result == QMessageBox.StandardButton.Retry)
            case _ : 
                self.changeTrayIcon(result)
                self.isWait = True
                result = QMessageBox.question(self,TITLE,result.description,QMessageBox.StandardButton.Retry,QMessageBox.StandardButton.Cancel)
                self.isWait = False
                if result != QMessageBox.StandardButton.Retry: sys.exit()
            
        

    # 初始化主界面
    def initWindow(self):
        self.setWindowTitle(TITLE)
        self.resize(400,300)
        self.setWindowIcon(self.sysIcon)

    #创建托盘图标
    def initTrayIcon(self):
        aRestore = QAction('主界面', self, triggered = self.showNormal)
        aQuit = QAction('退出', self, triggered = QCoreApplication.quit)
        
        menu = QMenu(self)
        menu.addAction(aRestore)
        menu.addAction(aQuit)
        
        self.trayIcon = QSystemTrayIcon(self)
        self.trayIcon.setIcon(self.sysIcon)
        self.trayIcon.setContextMenu(menu)
        self.trayIcon.show()
        self.trayIcon.activated[QSystemTrayIcon.ActivationReason].connect(self.openMainWindow)
    
    def openMainWindow(self, reason):
        # 双击打开主界面
        if reason.value == 3:
            self.showNormal()
            self.activateWindow()

if __name__ == '__main__':
    app=QApplication(sys.argv)
    QApplication.setQuitOnLastWindowClosed(False) # 关闭最后一个窗口不退出程序
    win=WinForm()
    win.show()
    sys.exit(app.exec())
