# STM32 Voice Command Recognition

![MCU](https://img.shields.io/badge/MCU-STM32F103-blue)
![Host](https://img.shields.io/badge/Host-Python%203-yellow)
![Platform](https://img.shields.io/badge/Platform-Embedded%20%7C%20Windows-green)
![DSP](https://img.shields.io/badge/DSP-MFCC%20%2B%20CMSIS--DSP-orange)
![License](https://img.shields.io/badge/License-not%20specified-lightgrey)

基于 STM32F103 和 Python 的四类语音命令识别示例。STM32 以 8 kHz 采集麦克风信号并计算 13 维 MFCC，通过 USART3/蓝牙串口发送给 Windows 上位机；Python 使用一维卷积神经网络识别 `left`、`right`、`stop` 和 `forward`。分类模型运行在电脑端，当前程序将识别结果打印到控制台。

## 核心模块

| 模块 | 文件 | 职责 |
| --- | --- | --- |
| ADC 采集 | `Hardware/AD.c` | 配置 ADC1 通道0，接收 PA0 上麦克风模块的模拟信号 |
| 定时采样与 DMA | `Hardware/MyDMA.c` | TIM3 以 8 kHz 触发 ADC；DMA 循环写入512个采样值，并用半传输/完成中断标记256点数据块 |
| MFCC | `Hardware/mfcc.c` | 去除直流分量、Hamming 加窗、256点 CMSIS FFT、功率谱、Mel 滤波和 DCT，输出13个系数 |
| 固件主流程 | `User/main.c` | 取稳定 DMA 数据块、计算并量化 MFCC、发送数据帧、更新 OLED |
| 串口协议解析 | `Host/voice_protocol.py` | 从任意长度的串口字节块中同步30字节帧，并按有符号大端格式解码13个系数 |
| 数据采集 | `Host/record_word_from_stm32.py` | 按命令类别采集连续特征帧，保存为一段录音一个二维 NumPy 文件 |
| 模型训练 | `Host/train_model_from_stm32.py` | 以录音段为单位划分训练、验证和测试集，训练并保存 CNN 与标准化参数 |
| 实时识别 | `Host/getNFCC.py` | 接收连续帧，执行与训练相同的缩放和标准化，输出类别或 `unknown` |

## 数据流

```text
麦克风 → PA0 / ADC1 → DMA循环缓冲区 → 256点音频块
       → MFCC(13维) → int16量化(×8) → USART3 / 蓝牙
       → Python串口解析 → 11帧特征窗口 → CNN → 四类命令
```

ADC 由 TIM3 固定以 8 kHz 触发。DMA 缓冲区分为两个256点半区；固件每隔一个半区计算并发送一帧，因此特征帧间隔为64 ms。每个串口数据包共30字节：`AA 55` 帧头、13个高字节在前的有符号 `int16` MFCC 系数、`0D 0A` 帧尾。量化比例是8，Python 解码后除以8。

## CNN 结构

每个输入样本包含11帧、每帧13个 MFCC 系数，形状为 `11×13`。模型依次使用64通道的一维卷积（卷积核宽度3）、批归一化、最大池化、128通道一维卷积、批归一化、全局平均池化、64单元全连接层，最后由 Softmax 输出四类概率。最高概率低于0.7时，实时程序返回 `unknown`。

## 快速开始

### 固件

1. 使用 Keil MDK 打开 `Project.uvprojx`。
2. 工程使用 STM32F10x Standard Peripheral Library 和 CMSIS-DSP 5.0.1。当前工程文件引用 Keil 安装目录中的 CMSIS Pack；若 Pack 不在工程预期的相对路径下，需要在 Keil 中调整 CMSIS 源文件和头文件路径。
3. 按硬件连接麦克风模拟输出至 PA0，蓝牙串口连接 USART3（PB10 TX、PB11 RX）。固件串口配置为9600波特率。
4. 编译并下载后，固件开始采样和发送 MFCC 特征。

### Python 上位机

要求 Windows 和 Python 环境。采集脚本使用 `msvcrt` 监听键盘操作。

```bash
python -m pip install -r Host/requirements.txt
```

将 `Host/record_word_from_stm32.py` 和 `Host/getNFCC.py` 中的 `PORT` 改为蓝牙对应的 COM 口，确认 HC-06 与 MCU 波特率一致。

1. 采集数据：运行 `python Host/record_word_from_stm32.py`。按 `1` 至 `4` 选择命令，回车开始和结束一段录音。每段至少保存11帧；每个类别至少录制5段独立录音。
2. 训练模型：运行 `python Host/train_model_from_stm32.py`。模型和标准化参数保存到 `Host/stm32_model.h5` 与 `Host/stm32_model_scaler.npz`。
3. 实时识别：运行 `python Host/getNFCC.py`。程序在控制台显示识别类别和置信度。

本固件的 MFCC 帧长和特征发送间隔已调整；应使用这版固件重新采集数据，并重新训练模型，不能直接沿用旧数据或旧模型。

## 依赖

`STM32F10x Standard Peripheral Library`、`CMSIS-DSP 5.0.1`、`pyserial`、`numpy`、`scikit-learn`、`tensorflow`。

## 许可

仓库尚未指定开源许可证。固件工程依赖的 ST 与 ARM/CMSIS 库遵循其各自的许可条款。
