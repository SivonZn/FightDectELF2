import sys
import os
import subprocess
import numpy
import cv2
import gpiod
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QTimer, Qt
import threading
from ultralytics import YOLO

class VideoDisplayApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg Video Display Application")
        self.setGeometry(100, 100, 1280, 720)
        
        # 初始化变量
        self.process = None
        self.timer = QTimer()
        self.camera_device = "/dev/video21"  # 确认这是正确的设备
        #self.camera_device = "beifen/test1.mp4"
        self.frame_width = 1280
        self.frame_height = 720
        rtsp_url = 'rtsp://192.168.1.236/live/yolo'  # RTSP服务器地址
        self.afsd = 0.0
        
        # 调试信息
        self.frame_count = 0
        self.last_error = ""
        
        self.initUI()

        self.model = YOLO("best-rk3588-04_rknn_model")
        self.model("output.jpg")

        self.chip = gpiod.Chip("gpiochip3")
        self.line = self.chip.get_line(27)
        self.line.request(consumer="LED_CONTROL", type=gpiod.LINE_REQ_DIR_OUT, default_val=0)

        self.ffmpeg_process = self.start_ffmpeg_rtsp(rtsp_url, 10)
        
    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 图像显示区域
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        main_layout.addWidget(self.image_label, 1)
        
        # 状态标签
        self.status_label = QLabel("Be Ready")
        self.status_label.setStyleSheet("color: gray;")
        main_layout.addWidget(self.status_label)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.load_image_btn = QPushButton("Loading Picture")
        self.load_image_btn.clicked.connect(self.load_image)
        button_layout.addWidget(self.load_image_btn)
        
        self.load_video_btn = QPushButton("Loading Video")
        self.load_video_btn.clicked.connect(self.load_video)
        button_layout.addWidget(self.load_video_btn)
        
        self.open_camera_btn = QPushButton("Open Camera")
        self.open_camera_btn.clicked.connect(self.open_camera)
        button_layout.addWidget(self.open_camera_btn)
        
        self.stop_btn = QPushButton("Pause")
        self.stop_btn.clicked.connect(self.stop)
        button_layout.addWidget(self.stop_btn)
        
        main_layout.addLayout(button_layout)
        
        # 定时器用于更新视频帧
        self.timer.timeout.connect(self.update_frame)
        
    def load_image(self):
        """加载并显示图片"""
        self.stop()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Picture", "", "Picture files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            self.status_label.setText(f"Loading Picture: {file_path}")
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                self.image_label.setPixmap(
                    pixmap.scaled(
                        self.image_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                )
    
    def load_video(self):
        """加载并播放视频"""
        self.stop()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select video", "", "video file  (*.mp4 *.avi *.mov *.mkv)"
        )
        
        if file_path:
            self.status_label.setText(f"Loading Video: {file_path}")
            command = [
                'ffmpeg',
                '-i', file_path,
                '-hwaccel', 'rkmpp', # RKMPP加速
                '-f', 'image2pipe',
                '-pix_fmt', 'bgr24',  # 修改为bgr24格式
                '-vcodec', 'rawvideo',
                '-vf', f'scale={self.frame_width}:{self.frame_height}',
                '-'
            ]
            self.start_ffmpeg_process(command)
    
    def open_camera(self):
        """打开摄像头"""
        self.stop()
        self.status_label.setText("Starting camera...")
        
        # 使用与ffplay相同的参数格式
        command = [
            'ffmpeg',
            '-f', 'v4l2',
            '-framerate', '10',           # 添加帧率
            '-video_size', '1280x720',    # 明确指定分辨率
            '-input_format', 'mjpeg',     # 尝试MJPEG格式
            '-i', self.camera_device,
            '-f', 'image2pipe',
            '-pix_fmt', 'bgr24',          # 修改为bgr24格式
            '-vcodec', 'rawvideo',
            '-vf', f'scale={self.frame_width}:{self.frame_height}',
            '-r', '10',
            '-'
        ]
        # command = [
        #         'ffmpeg',
        #         '-i', self.camera_device,
        #         '-hwaccel', 'rkmpp', # RKMPP加速
        #         '-f', 'image2pipe',
        #         '-pix_fmt', 'bgr24',  # 修改为bgr24格式
        #         '-vcodec', 'rawvideo',
        #         '-vf', f'scale={self.frame_width}:{self.frame_height}',
        #         '-'
        #     ]
        
        self.start_ffmpeg_process(command, fps=10)

    def start_ffmpeg_process(self, command, fps=10):
        """启动FFmpeg进程"""
        self.stop()
        
        self.timer.start(int(1000 / fps))  # 动态计算间隔

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8,
            shell=False
        )
        
        # 启动线程读取错误输出
        def read_stderr():
            while self.process and self.process.poll() is None:
                err = self.process.stderr.readline()
                if err:
                    err_str = err.decode().strip()
                    print("FFmpeg:", err_str)
                    self.last_error = err_str
                    self.status_label.setText(f"Error: {err_str[:50]}...")
        
        threading.Thread(target=read_stderr, daemon=True).start()
        
        # 启动定时器
        self.timer.start(33)  # ~30fps
        self.frame_count = 0
        self.status_label.setText("on-air...")
    
    def start_ffmpeg_rtsp(self, rtsp_url, fps=30):
        """启动FFmpeg进程用于RTSP推流"""
        command = [
            'ffmpeg',
            '-y',  # 覆盖输出文件
            '-f', 'rawvideo',  # 输入格式
            '-vcodec', 'rawvideo',  # 输入编解码器
            '-pix_fmt', 'bgr24',  # OpenCV使用的像素格式
            '-s', f'{self.frame_width}x{self.frame_height}',  # 帧尺寸
            '-r', str(fps),  # 帧率
            '-i', '-',  # 从标准输入读取
            '-c:v', 'h264_rkmpp',  # 输出编码器
            '-f', 'rtsp',  # 输出格式
            '-rtsp_transport', 'tcp',  # 使用TCP传输
            rtsp_url
        ]
        return subprocess.Popen(command, stdin=subprocess.PIPE)

    def get_max_prob_for_class0(self, results):
            """
            从YOLO推理结果中获取class0对象的最大概率
            
            参数:
                results: YOLO模型的推理结果(可以是v5或v8的输出)
            
            返回:
                float: class0对象的最大概率，如果没有class0对象则返回0
            """
            max_prob = 0.0
            
            for box in results.boxes:
                print(int(box.cls))
                if int(box.cls) == 0:  # 检查是否为class0
                    conf = float(box.conf)
                    if conf > max_prob:
                        max_prob = conf
            print(max_prob)    
            return max_prob if max_prob > 0 else 0.0

    def update_frame(self):
        """从FFmpeg进程更新帧"""
        if not self.process:
            return
            
        frame_size = self.frame_width * self.frame_height * 3

        # 读取一帧数据
        raw_frame = self.process.stdout.read(frame_size)
        
        # 检查帧数据是否完整
        if len(raw_frame) != frame_size:
            error_msg = f"Incomplete frame data: {len(raw_frame)}/{frame_size} bytes"
            if not raw_frame:
                error_msg = "No frame data received"
            print(error_msg)
            self.status_label.setText(error_msg)
            self.stop()
            return
            
        # 转换为 NumPy 数组
        img = numpy.frombuffer(raw_frame, numpy.uint8).reshape([self.frame_height, self.frame_width, 3])

        # 直接进行推理
        result = self.model(img)
        annotated = result[0].plot()

        # 将BGR直接转换为RGB格式
        rgb_annotated = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)

        self.ffmpeg_process.stdin.write(annotated.tobytes())

        # 转换为QImage
        image = QImage(
            rgb_annotated.data, 
            self.frame_width, 
            self.frame_height,
            3 * self.frame_width,
            QImage.Format_RGB888
        )
        
        # 转换为QPixmap并显示
        pixmap = QPixmap.fromImage(image)
        self.image_label.setPixmap(
            pixmap.scaled(
                self.image_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )
        
        self.afsd = self.afsd + (5 ** self.get_max_prob_for_class0(result[0]))
        print("Mutil" + str(self.afsd))

        # 更新帧计数
        self.frame_count += 1
        if self.frame_count % 10 == 0:
            self.status_label.setText(f"Playing ... Frame: {self.frame_count}")

        if(self.frame_count % 50 == 0):
            if(self.afsd > 150):
                print("Detected!")
                self.line.set_value(0)
                self.afsd = 0.0
            else:
                print("Safe!")
                self.line.set_value(1)
                self.afsd = 0.0

    def stop(self):
        """停止所有播放"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except:
                try:
                    self.process.kill()
                except:
                    pass
            finally:
                self.process = None
                
        self.timer.stop()
        if not self.last_error:
            self.status_label.setText("stopped")
        
    def closeEvent(self, event):
        """窗口关闭时清理资源"""
        self.stop()
        event.accept()

if __name__ == "__main__":
    os.environ["QT_QPA_PLATFORM"] = "eglfs"
    app = QApplication(sys.argv)
    window = VideoDisplayApp()
    window.show()
    sys.exit(app.exec_())
