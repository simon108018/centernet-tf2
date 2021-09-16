import numpy as np
import os

from datetime import datetime
import tensorflow as tf
import tensorflow_addons as tfa
from tensorflow import keras
from tensorflow.keras.callbacks import (EarlyStopping, ReduceLROnPlateau,
                                        TensorBoard)
from utils.utils import ModelCheckpoint
from nets.onenet_generator import Generator
from nets.onenet import onenet

gpus = tf.config.experimental.list_physical_devices(device_type='CPU')
# for gpu in gpus:
#     tf.config.experimental.set_memory_growth(gpu, True)


def new_log(logdir):
    list_ = os.listdir(logdir)
    list_.sort(key=lambda fn: os.path.getmtime(logdir + '/' + fn))
    list_ = [l for l in list_ if '.h5' in l]
    # 获取文件所在目录
    if list_:
        newlog = os.path.join(logdir, list_[-1])
    else:
        newlog = None
    return newlog


#---------------------------------------------------#
#   获得类
#---------------------------------------------------#
def get_classes(classes_path):
    '''loads the classes'''
    with open(classes_path) as f:
        class_names = f.readlines()
    class_names = [c.strip() for c in class_names]
    return class_names

#----------------------------------------------------#
#   检测精度mAP和pr曲线计算参考视频
#   https://www.bilibili.com/video/BV1zE411u7Vw
#----------------------------------------------------#
if __name__ == "__main__":
    #-----------------------------#
    #   图片的大小
    #-----------------------------#
    input_shape = [416, 416, 3]
    #-----------------------------#
    #   训练前一定要注意修改
    #   classes_path对应的txt的内容
    #   修改成自己需要分的类
    #-----------------------------#
    classes_path = 'model_data/coco_classes.txt'
    #----------------------------------------------------#
    #   获取classes和数量
    #----------------------------------------------------#
    class_names = get_classes(classes_path)
    num_classes = len(class_names)
    #-----------------------------#
    #   主干特征提取网络的选择
    #   resnet18
    #   resnet50
    #-----------------------------#
    backbone = "resnet18"

    #----------------------------------------------------#
    #   获取onenet模型
    #----------------------------------------------------#
    model = onenet(input_shape, num_classes=num_classes, backbone=backbone, mode='train')
    #------------------------------------------------------#
    #   权值文件请看README，百度网盘下载
    #   训练自己的数据集时提示维度不匹配正常
    #   预测的东西都不一样了自然维度不匹配
    #------------------------------------------------------#
    if backbone == "resnet50":
        path = './logs50'
    elif backbone == "resnet18":
        path = './logs18'

    model_path = new_log(path)
    if model_path:
        model.load_weights(model_path, by_name=True, skip_mismatch=True)
        print('successful load weights from {}'.format(model_path))
    #----------------------------------------------------#
    #   获得图片路径和标签
    #----------------------------------------------------#
    annotation_path = '2007_train.txt'
    #----------------------------------------------------------------------#
    #   验证集的划分在train.py代码里面进行
    #   2007_test.txt和2007_val.txt里面没有内容是正常的。训练不会使用到。
    #   当前划分方式下，验证集和训练集的比例为1:9
    #----------------------------------------------------------------------#
    val_split = 0.1
    with open(annotation_path) as f:
        lines = f.readlines()
    np.random.seed(123)
    np.random.shuffle(lines)
    np.random.seed(None)
    num_val = int(len(lines)*val_split)
    num_train = len(lines) - num_val

    #-------------------------------------------------------------------------------#
    #   训练参数的设置
    #   logging表示tensorboard的保存地址
    #   checkpoint用于设置权值保存的细节，period用于修改多少epoch保存一次
    #   reduce_lr用于设置学习率下降的方式
    #   early_stopping用于设定早停，val_loss多次不下降自动结束训练，表示模型基本收敛
    #-------------------------------------------------------------------------------#
    if backbone == "resnet50":
        logging = TensorBoard(log_dir="logs50")
        checkpoint = ModelCheckpoint('logs50/ep{epoch:03d}-loss{loss:.3f}-val_loss{val_loss:.3f}.h5',
                                     monitor='val_loss', save_weights_only=True, save_best_only=False, period=1)
    elif backbone == "resnet18":
        logs = "logs18/" + datetime.now().strftime("%Y%m%d-%H%M%S")
        logging = TensorBoard(log_dir=logs, profile_batch=2, histogram_freq=1)
        checkpoint = ModelCheckpoint('logs18/ep{epoch:03d}-loss{loss:.3f}-val_loss{val_loss:.3f}.h5',
                                     monitor='val_loss', save_weights_only=True, save_best_only=False, period=1)
    else:
        logging = TensorBoard(log_dir="logs")
        checkpoint = ModelCheckpoint('logs/ep{epoch:03d}-loss{loss:.3f}-val_loss{val_loss:.3f}.h5',
                                     monitor='val_loss', save_weights_only=True, save_best_only=False, period=1)

    Batch_size = 32
    Init_Epoch = 36
    Epoch = 150
    step_num_per_epoch = num_train // Batch_size
    step = tf.Variable(num_train//Batch_size * Init_Epoch, trainable=False)
    schedule = tf.optimizers.schedules.PiecewiseConstantDecay(
        [115*step_num_per_epoch, 140*step_num_per_epoch], [1e-0, 1e-1, 1e-2])
    # lr and wd can be a function or a tensor
    lr = 5e-4 * schedule(step)
    wd = lambda: 1e-4 * schedule(step)
    optimizer = tfa.optimizers.AdamW(learning_rate=lr, weight_decay=wd)
    gen = Generator(Batch_size, lines[:num_train], lines[num_train:], input_shape, num_classes)
    # radam = tfa.optimizers.RectifiedAdam(learning_rate=Lr,
    #                                      total_steps=150000,
    #                                      weight_decay=1e-4,
    #                                      warmup_proportion=0.1,
    #                                      min_lr=Lr * 1e-3)
    # ranger = tfa.optimizers.Lookahead(radam, sync_period=6, slow_step_size=0.5)
    model.compile(
        loss={'cls': lambda y_true, y_pred: y_pred, 'loc': lambda y_true, y_pred: y_pred, 'giou': lambda y_true, y_pred: y_pred},
        loss_weights=[2, 5, 2],
        optimizer=optimizer)

    model.fit(gen.generate(True),
                        steps_per_epoch=num_train//Batch_size,
                        validation_data=gen.generate(False),
                        validation_steps=num_val//Batch_size,
                        epochs=Epoch,
                        verbose=1,
                        initial_epoch=Init_Epoch,
                        callbacks=[logging, checkpoint])








