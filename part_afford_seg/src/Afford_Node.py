#!/usr/bin/env python3
import cv2
from matplotlib.pyplot import box
import rospy
from cv_bridge import CvBridge, CvBridgeError
from sensor_msgs.msg import Image as msg_Image

from tool.utils import *
from tool.torch_utils import *
from tool.darknet2pytorch import Darknet
import torch
import argparse
from seg_model import build_seg_model

from affordance2.msg import bbox, bboxes
from affordance2.msg import seg_out, center

show_all_mask = True

def get_centroid(th):
    contours, hierarchy = cv2.findContours(th,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    areas = [cv2.contourArea(c) for c in contours]
    max_index = np.argmax(areas)
    cnt=contours[max_index]
    M=cv2.moments(cnt)
    cx=int(M['m10']/M['m00'])
    cy=int(M['m01']/M['m00'])
    return [cx,cy]

def thresh_mask_screw(grid_image):
    # print()
    c1_th = grid_image[:,:,2] >= 0.50196078
    c2_th = grid_image[:,:,1] >= 0.50196078

    c1_th = np.array(c1_th, dtype = np.uint8)*255
    c2_th = np.array(c2_th, dtype = np.uint8)*255

    c1_c = get_centroid(c1_th)
    c2_c = get_centroid(c2_th)
    
    angle = math.atan2(c2_c[1]-c1_c[1], c1_c[0]-c2_c[0])
    return c1_c, c2_c, angle*180/math.pi

def thresh_mask_terminal(grid_image):

    c1_th = grid_image[:,:,0] >= 0.50196078 
    c2_th = grid_image[:,:,1] >= 0.50196078

    c1_th = np.array(c1_th, dtype = np.uint8)*255
    c2_th = np.array(c2_th, dtype = np.uint8)*255

    c1_c = get_centroid(c1_th)
    c2_c = get_centroid(c2_th)
    
    angle = math.atan2(c2_c[1]-c1_c[1], c1_c[0]-c2_c[0])

    return c1_c, c2_c, angle*180/math.pi

class Afford_Node:
    def __init__(self) -> None:
        rospy.init_node("Afford_Node")
        self.bridge = CvBridge()
        self.seg_m = build_seg_model(model="mobilenet", class_num=6, ckpt="./111_project/components_20220427.pth")
        rospy.Subscriber("/camera/color/image_raw_workspace", msg_Image, self.imageCallback)
        rospy.Subscriber("/yolov4_bboxes", bboxes, self.bboxes_Callback)
        self.pub = rospy.Publisher('/seg_out', seg_out, queue_size=1)

    def imageCallback(self, img_msg):
        self.cv_image = self.bridge.imgmsg_to_cv2(img_msg, "bgr8")

    def bboxes_Callback(self, bbox_msg):
        n = 0
        seg_o = seg_out() 
        need_seg_class = [0,3,4]

        if show_all_mask:
            mask_all = np.zeros((430,660,3))

        for bb in bbox_msg.bboxes:
            roi = self.cv_image[bb.ymin:bb.ymax, bb.xmin:bb.xmax]

            if bb.class_ in need_seg_class:
                grid_image = self.seg_m.run(roi)
                grid_image = cv2.resize(grid_image, (bb.xmax-bb.xmin, bb.ymax-bb.ymin))
                cv_im = self.bridge.cv2_to_imgmsg(grid_image, "64FC3")
                seg_o.roi.append(cv_im)
            else:
                grid_image = np.zeros((bb.ymax-bb.ymin, bb.xmax-bb.xmin,3))
                cv_im = self.bridge.cv2_to_imgmsg(grid_image, "64FC3")
                seg_o.roi.append(cv_im)


            if bb.class_ == 0:
                c = center()
                c1_c, c2_c, angle = thresh_mask_screw(grid_image)
                c.check = True
                c.c1_x = c1_c[0]
                c.c1_y = c1_c[1]
                c.c2_x = c2_c[0]
                c.c2_y = c2_c[1]
                c.angle = angle
                seg_o.centers.append(c)

            if bb.class_ == 1 or bb.class_ == 2 :
                c = center()
                c.check = False
                seg_o.centers.append(c)
            
    
            if bb.class_ == 3 or bb.class_ == 4:
                c = center()
                c1_c, c2_c, angle = thresh_mask_terminal(grid_image)
                c.check = True
                c.c1_x = c1_c[0]
                c.c1_y = c1_c[1]
                c.c2_x = c2_c[0]
                c.c2_y = c2_c[1]
                c.angle = angle
                seg_o.centers.append(c)            

            cv2.imshow(str(n), grid_image)
            cv2.waitKey(1)
            n+=1 

            if show_all_mask:
                mask_all[bb.ymin:bb.ymax, bb.xmin:bb.xmax] += grid_image
                if c.check == True:
                    cv2.circle(mask_all, (c.c1_x+bb.xmin, c.c1_y+bb.ymin), 2, (1, 227, 254), -1)
                    cv2.circle(mask_all, (c.c2_x+bb.xmin, c.c2_y+bb.ymin), 2, (1, 227, 254), -1)
                    cv2.putText(mask_all, str(round(c.angle,2)), (c.c1_x+bb.xmin, c.c1_y+bb.ymin),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
        self.pub.publish(seg_o)

        if show_all_mask:
            cv2.imshow("mask_all", mask_all)

        

if __name__ == "__main__":
    Afford_Node()
    rospy.spin()