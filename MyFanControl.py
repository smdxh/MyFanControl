from controlTool import *
import sys
from PyQt6.QtCore import QCoreApplication,QTimer,Qt,QThread,pyqtSignal
from PyQt6.QtGui import QIcon,QAction
from PyQt6.QtWidgets import (QApplication,QMainWindow,QSystemTrayIcon,QMenu,QTabWidget,QSpinBox,QHBoxLayout,
QLabel,QGridLayout,QWidget,QCheckBox,QMessageBox,QSlider,QVBoxLayout,QPushButton)
from PIL import Image, ImageDraw
# from pyqtgraph import PlotWidget, plot
from matplotlib import pyplot,figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
# from PyQtDarkTheme import DarkStyle
import numpy as np
TITLE = "机箱风扇控制器3.2"
maxTemperature = 120
minTemperature = 0

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
        self.isMessageBox = False # 弹窗提示待处理
        self.movePointIndex = None # 折线图中准备拖拽的点的下标
        self.temperatureList = getListConfig('USER','temperature_list')
        #折线图加上头尾两个不可修改的点
        self.temperatureList.append(maxTemperature)
        self.temperatureList.insert(0,minTemperature)
        self.dutyRatioList = getListConfig('USER','duty_ratio_list')
        self.dutyRatioList.append(100)
        self.dutyRatioList.insert(0,0)
        self.dutyRatio = conf.getint('USER','duty_ratio')
        self.initWindow()
        self.initTrayIcon()
        self.initUI()

    # 初始化主界面UI
    def initUI(self):
        self.label1 = QLabel("CPU温度：获取中...")
        self.label2 = QLabel("GPU温度：获取中...")
        self.label3 = QLabel("占空比：获取中...")
        self.label4 = QLabel("返回结果：获取中...")
        self.label5 = QLabel("Author：smdxh")
        self.label5.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.tabs = QTabWidget()# Initialize tab screen
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        # self.tabs.resize(300,200)

        self.cb1 = QCheckBox('读写超时提示',self)
        self.cb2 = QCheckBox('PWM设备错误提示',self)
        self.dragAdjustDutyRatio = QCheckBox('拖动调整占空比',self)

        # Add tabs
        self.tabs.addTab(self.tab1,"默认")
        self.tabs.addTab(self.tab2,"折线图")
        self.tabs.setCurrentIndex(conf.getint('USER','tabs_index'))
        self.tabs.currentChanged.connect(self.changeTab)

        self.tab1UI()
        self.tab2UI()

        self.cb1.setChecked(conf.getint('USER','TIMEOUT_EXCEPTION'))
        self.cb2.setChecked(conf.getint('USER','RETURN_ERROR'))
        self.dragAdjustDutyRatio.setChecked(conf.getint('USER','manual'))

        mylayout = QGridLayout(self)
        mylayout.addWidget(self.label1,0,0)
        mylayout.addWidget(self.label2,1,0)
        mylayout.addWidget(self.label3,2,0)
        mylayout.addWidget(self.label4,4,0)
        mylayout.addWidget(self.cb1,0,1)
        mylayout.addWidget(self.cb2,1,1)
        mylayout.addWidget(self.dragAdjustDutyRatio,2,1)
        mylayout.addWidget(self.label5,4,1)
        mylayout.addWidget(self.tabs,3,0,1,2,alignment=Qt.AlignmentFlag.AlignVCenter)

        self.cb1.stateChanged.connect(self.changecb1)
        self.cb2.stateChanged.connect(self.changecb2)
        self.dragAdjustDutyRatio.stateChanged.connect(self.changecb3)
        self.s.sliderPressed.connect(self.changes) # 点击滑块
        self.s.sliderMoved.connect(self.changes) # 拖动滑块
        self.s.actionTriggered.connect(self.changes) # 点击滑动条
        self.s.valueChanged.connect(self.changeDutyRatio) # 点击滑动条
        self.s.setValue(conf.getint('USER','duty_ratio'))
        # self.s.mousePressEvent(self.changes)
        # self.s.sliderPressed.connect(self.changes)
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

    def clickButton(self):
        sender = self.sender()
        if sender.text() == '保存':
            conf.set('USER','begin_temperature',str(self.sp1.value()))
            saveConfig('USER','max_temperature',str(self.sp2.value()))
        # print(sender.text() + '被点击')
    def tab2UI(self):
        self.tab2layout = QVBoxLayout(self)
        self.tab2.setLayout(self.tab2layout)
        self.figure = pyplot.figure()
        # self.figure.set_alpha(0)
        # self.figure.patch.set_alpha(0) #设置画布透明
        self.canvas = FigureCanvas(self.figure)
        # self.canvas.mpl_disconnect(self.canvas.manager.key_press_handler_id)  # 取消默认快捷键的注册，(没有这玩意)
        self.canvas.mpl_connect('button_press_event', self.on_button_press)#鼠标点击事件 
        self.canvas.mpl_connect('button_release_event', self.on_button_release)#鼠标松开
        # self.canvas.setContentsMargins(100,0,0,100)
        self.tab2layout.addWidget(self.canvas)
        self.ax = self.figure.add_subplot(111)
        # self.ax.spines['left'].set_alpha(0) # 表格上下左右框的线透明了
        # self.ax.patch.set_alpha(0) #设置绘图区域透明
        pyplot.gcf().subplots_adjust(left=0.2,top=0.9,bottom=0.25, right=0.9)
        # pyplot.style.use('dark_background')
        # self.ax.set_facecolor('#FFFFFF')
        self.setPlotAttribute()
        # self.figure.
        self.canvas.draw()
    def setPlotAttribute(self):
        # self.ax.set_alpha(0)
        self.ax.set_xlabel('Temperature(℃)',loc='right')
        self.ax.set_ylabel('DutyRadio(%)',loc='top')
        self.ax.plot(self.temperatureList,self.dutyRatioList,marker='s')
        self.ax.grid(True)
        self.ax.set_xlim(minTemperature,maxTemperature) # 坐标范围
        self.ax.set_ylim(0,100)

        #鼠标释放事件，鼠标松开的时候，就把上面鼠标点击并且移动的关系解绑  这样鼠标松开的时候 就不会拖动点了
    def on_button_release(self,event):
        self.canvas.mpl_disconnect(self.canvas.mpl_connect('motion_notify_event', self.on_button_move))  # 鼠标释放事件
        if self.movePointIndex != None:
            conf.set('USER','temperature_list',str(self.temperatureList[1:-1]))
            saveConfig('USER','duty_ratio_list',str(self.dutyRatioList[1:-1]))
        self.movePointIndex = None
    # 鼠标点击事件  函数里面又绑定了一个鼠标移动事件，所以生成的效果是鼠标按下并且移动的时候
    def on_button_press(self,event):
        if event.button==1:#1、2、3分别代表鼠标的左键、中键、右键
            x_mouse, y_mouse= event.xdata, event.ydata#拿到鼠标当前的横纵坐标
            if not x_mouse :return #鼠标点到外面了
            x,y = self.temperatureList,self.dutyRatioList
            oldD = 100 
            #计算一下鼠标的位置和图上点的位置距离，如果距离很近就移动图上那个点
            for i in range(1,len(x)-1):
                #计算一下距离 图上每个点都和鼠标计算一下距离
                d = (x_mouse -x[i] ) **2 + (y_mouse -y[i]) ** 2
                if d<25 and d < oldD:#这里设置一个阈值，如果距离很近，就把它添加到那个列表中去，选出最近的点
                    self.movePointIndex = i
                    oldD = d # 选出最近的点
            if self.movePointIndex:
                self.canvas.mpl_connect('motion_notify_event', self.on_button_move)
    def on_button_move(self,event):
            # print(self.movePointIndex , event)
            ind = self.movePointIndex
            if event.xdata:
                x_mouse, y_mouse= round(event.xdata), round(event.ydata)#拿到鼠标当前的横纵坐标
                if x_mouse <= self.temperatureList[ind-1] : x_mouse = self.temperatureList[ind-1] + 1
                if x_mouse >= self.temperatureList[ind+1] : x_mouse = self.temperatureList[ind+1] - 1
                self.temperatureList[ind] = x_mouse
                self.dutyRatioList[ind] = y_mouse
        #         #拟合好了以后把曲线画出来
                self.ax.cla()
                self.setPlotAttribute()
                self.ax.text(x_mouse,y_mouse,'(%d,%d)'%(x_mouse,y_mouse))
                self.canvas.draw()  # 重新绘制整个图表，所以看到的就是鼠标移动点然后曲线也跟着在变动

    def tab1UI(self):         
        self.tab1layout = QVBoxLayout(self)
        self.tab1.setLayout(self.tab1layout)
        self.tab1layout.addWidget(QLabel("自动调整占空比："))

        mylayout = QGridLayout(self)
        autowidget = QWidget()
        autowidget.setLayout(mylayout)
        l1 = QLabel("启动温度：")
        l1.setAlignment(Qt.AlignmentFlag.AlignRight)
        l1.setContentsMargins(0,3,0,0)
        mylayout.addWidget(l1,0,0)
        self.sp1 = QSpinBox()
        l1.setBuddy(self.sp1) #伙伴控件
        self.sp1.setValue(conf.getint('USER','begin_temperature'))
        self.sp1.setRange(0,199)
        self.sp1.valueChanged.connect(self.valueChange1)
        mylayout.addWidget(self.sp1,0,1)
        l2 = QLabel("满转温度：")
        l2.setAlignment(Qt.AlignmentFlag.AlignRight)
        l2.setContentsMargins(0,3,0,0)
        mylayout.addWidget(l2,0,2)
        self.sp2 = QSpinBox()
        l2.setBuddy(self.sp2) #伙伴控件
        self.sp2.setValue(conf.getint('USER','max_temperature'))
        self.sp2.setRange(1,120)
        self.sp2.valueChanged.connect(self.valueChange2)
        mylayout.addWidget(self.sp2,0,3)

        button1 = QPushButton('保存')
        button1.clicked.connect(self.clickButton)
        mylayout.addWidget(button1,1,3)

        self.tab1layout.addWidget(autowidget)
        self.tab1layout.addWidget(QLabel("拖动调整占空比："))
        self.s = QSlider(Qt.Orientation.Horizontal)
        self.s.setMaximum(100)
        self.s.setMinimum(0)
        self.s.setPageStep(10)
        self.s.setSingleStep(1)
        self.s.setTickInterval(10) #刻度间隔
        self.s.setTickPosition(QSlider.TickPosition.TicksBelow) #在（水平）滑块下方绘制刻度线

        self.tab1layout.addWidget(self.s)
  
    # 输入框变化
    def valueChange1(self,a):
        self.dragAdjustDutyRatio.setChecked(Qt.CheckState.Unchecked.value)
        if self.sp2.value() <= a : self.sp2.setValue(a + 1) 
    # 手动调整占空比
    def changeDutyRatio(self,a):
        saveConfig('USER','duty_ratio',str(a))   
    # 输入框变化
    def changeTab(self,a):
        if a == 0:
            self.dragAdjustDutyRatio.setEnabled(True)
        else:
            self.dragAdjustDutyRatio.setEnabled(False)
        saveConfig('USER','tabs_index',str(a))
    # 输入框变化
    def valueChange2(self,a):
        self.dragAdjustDutyRatio.setChecked(Qt.CheckState.Unchecked.value)
        if a <= self.sp1.value() : self.sp1.setValue(a - 1)
    # 勾选框变化
    def changecb1(self,a):
        saveConfig('USER','TIMEOUT_EXCEPTION',str(a))
    # 勾选框变化
    def changecb2(self,a):
        saveConfig('USER','RETURN_ERROR',str(a))
    # 勾选框变化
    def changecb3(self,a):
        saveConfig('USER','manual',str(a))
    # 滑动条变化
    def changes(self):
        self.dragAdjustDutyRatio.setChecked(Qt.CheckState.Checked.value)
    # 测试用例
    def testChange(self,a):
        sender = self.sender()
        print(sender,a)
        # self.dragAdjustDutyRatio.setChecked(Qt.CheckState.Checked.value)

    # 更新主界面内容
    def updateUI(self):
        gpuTem = getGPUTemp()
        cpuTem = getCPUTemp()
        maxTem = gpuTem
        if cpuTem > gpuTem : maxTem = cpuTem
        match self.tabs.currentIndex():
            case 0:
                if self.dragAdjustDutyRatio.isChecked():
                    self.dutyRatio = self.s.value()
                else:
                    self.dutyRatio = round((maxTem-self.sp1.value()) * (100/(self.sp2.value()-self.sp1.value())))
            case 1:
                xdata = self.ax.lines[0].get_xdata()
                ydata = self.ax.lines[0].get_ydata()
                for i in range(len(xdata)):
                    if xdata[i] > maxTem:
                        x1,y1 = xdata[i-1],ydata[i-1]
                        x2,y2 = xdata[i],ydata[i]
                        k = (y1-y2)/(x1-x2)
                        b = y1 - k * x1
                        self.dutyRatio = round(k*maxTem+b)
                        break
            case _:
                print('error') 
        self.label1.setText("CPU温度：%d" %cpuTem)
        self.label2.setText("GPU温度：%d" %gpuTem)
        if self.mythread.isRunning() :
            self.label4.setText("返回结果：%s" %"PWM设置中")
        elif self.isMessageBox == True:
            self.label4.setText("返回结果：%s" %"错误待处理")
        else:
            self.mythread = setPWMThread(data=self.dutyRatio) #设置风扇占空比
            self.mythread.data_sent.connect(self.on_data_received)
            self.mythread.start()
        

    def on_data_received(self,result):
        self.result = result
        self.label3.setText("占空比：%s" %result.dutyRatio)
        if not self.dragAdjustDutyRatio.isChecked():
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
                    self.isMessageBox = True
                    result = QMessageBox.question(self,TITLE,result.description,QMessageBox.StandardButton.Retry,QMessageBox.StandardButton.Cancel)
                    self.isMessageBox = False
                    self.cb1.setChecked(result == QMessageBox.StandardButton.Retry)
            case PWMResponse.RETURN_ERROR : 
                self.changeTrayIcon(result)
                if self.cb2.isChecked():
                    self.isMessageBox = True
                    result = QMessageBox.question(self,TITLE,result.description,QMessageBox.StandardButton.Retry,QMessageBox.StandardButton.Cancel)
                    self.isMessageBox = False
                    self.cb2.setChecked(result == QMessageBox.StandardButton.Retry)
            case _ : 
                self.changeTrayIcon(result)
                self.isMessageBox = True
                result = QMessageBox.question(self,TITLE,result.description,QMessageBox.StandardButton.Retry,QMessageBox.StandardButton.Cancel)
                self.isMessageBox = False
                if result != QMessageBox.StandardButton.Retry: sys.exit()
            
        

    # 初始化主界面
    def initWindow(self):
        self.setWindowTitle(TITLE)
        self.resize(400,350)
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
    app.setStyle('fusion')
    QApplication.setQuitOnLastWindowClosed(False) # 关闭最后一个窗口不退出程序
    win=WinForm()
    win.show()
    sys.exit(app.exec())
