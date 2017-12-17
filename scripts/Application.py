# -*- coding: utf-8 -*-

import numpy as np
import cv2

from skimage import io, filters, feature, img_as_ubyte, morphology, exposure
from scipy.ndimage.morphology import binary_fill_holes

import Detection as detect
import Utils
import Training
import Classification
import types  
import IO
import Defects
import sys


print("Process started")

# image of palette
imname = sys.argv[1]
im = cv2.imread(imname, 1)

im = Utils.adjust_position(im)
im = Utils.adjust_resolution(im)


# Setting some relevant informations that are going to be returned to server through JSON dictionary...
IO.set_outputs(im)


# Check if the palette has a defect. Currently there are 6 implementations of defects analysis:
# low brightness, missing borders, out of focus, shadows and water on the surface. Some of them are detected using deep learning algorithm.
if Defects.isBlurred(im) < 11.0:
	print(IO.json_packing_error('ERR_001'))
	exit()

if Defects.isDark(im) < 110.0:
	print(IO.json_packing_error('ERR_002'))
	exit()


# The first step is to check if the image really has a pallete with a circle at its center.
im = Defects.hasPalette(im)
if type(im) == type(""):
	exit()


# Watermark detection.
if Defects.watermark_detection(im) == True:
	print(IO.json_packing_error('ERR_007'))
	exit()



print("Detecting circle...\n")

# detecting the central circle
# The program will try to recognize the central circle in 3 attempts.
# In case the circle isn't yet recognized, we stop the execution

params = None
for att in range(15):
	params = detect.detect_circle_mark(im)

	if type(params) == type(None):
		
		if att == 14:
			print(IO.json_packing_error('ERR_003'))
			exit()
		else:
			continue

	else:
		break


# getting a copy of the original image
imcpy = im.copy()

# reducing contrast between central circle and background...
im = detect.remove_central_circle(im, params)

# crop both original and edited versions to a workable region.
im = Utils.crop_image(im, params)
imcpy = Utils.crop_image(imcpy, params)

# reducing contrast between the lines at the border of the palette and the background!
im = detect.remove_border_lines(im)
gsimage = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)


# Check if the croped image has shadows or something else that might
# hinder the egg recognition
if Defects.shadow_index(im) > 0.13:
	print(IO.json_packing_error('ERR_004'))
	exit()


print("Performing segmentation...")


# detect borders using canny
cbimage = feature.canny(gsimage, sigma=3)
bimage = img_as_ubyte(cbimage) # converting image format to unsigned byte
bimage = detect.closing_gaps(bimage) # closing gaps...


# extracting the features...
# ============================================================== BORDER SIZE
# get perimeter of everything is in the image

print("Performing border detection...")
objects = detect.object_detection(bimage)

eggs, clusters = Classification.border_lenght_classification(objects, params[2])



# ============================================================== BORDER SHAPE
# checking the shapes of eggs...

print("Performing shape detection...\n")

shapes = []
for i in range(len(eggs)):
	shapes.append(detect.shape_detection(eggs[i]) / params[2])

shapesc = []
for i in range(len(clusters)):
	shapesc.append(detect.shape_detection(clusters[i]) / params[2])


#Training.border_shape(bimage, eggs, shapes, "sh.dat")
#Training.border_shape(bimage, clusters, shapesc, "shcls.dat")

eggs = Classification.border_shape_classification(shapes, eggs, "sh.dat")
clusters = Classification.border_shape_classification(shapesc, clusters, "shcls.dat")



# ============================================================== BORDER COLOR
# Get colors info of remaining objects...

print("\nPerforming color detection...")

areas_egg = []
areas_clusters = []

imHSV = cv2.cvtColor(imcpy, cv2.COLOR_BGR2HSV)
imLAB = cv2.cvtColor(imcpy, cv2.COLOR_BGR2LAB)

for i in range(len(eggs)):
	areas_egg.append(detect.get_object_area(eggs[i], bimage))

for i in range(len(clusters)):
	areas_clusters.append(detect.get_object_area(clusters[i], bimage))


ecolors = detect.get_object_color(areas_egg, imcpy, imHSV, imLAB)
ccolors = detect.get_object_color(areas_clusters, imcpy, imHSV, imLAB)

#Training.object_color(im, eggs, ecolors, True)
#Training.object_color(im, clusters, ccolors, False)

eggs = Classification.object_color_classification(ecolors, eggs, True)
clusters = Classification.object_color_classification(ccolors, clusters, False)

print("Color - Eggs: " + str(len(eggs)))
print("Color - Clusters: " + str(len(clusters)))



# ============================================================== COMPUTATION
# Get the total number of eggs!
# Once the amount of eggs and clusters might be changed, we must to re-calculate their area.
# We use it to compute how many eggs fits in a cluster.

areas_egg = []
areas_clusters = []

for i in range(len(eggs)):
	areas_egg.append(detect.get_object_area(eggs[i], bimage))

for i in range(len(clusters)):
	areas_clusters.append(detect.get_object_area(clusters[i], bimage))


# Estimation of the mean area of the eggs in this sample.
eggs_size_avg = 0
total_eggs = 0

if len(eggs) > 0:
	total_eggs = len(eggs)

	for egg in areas_egg:
		eggs_size_avg += len(egg)

	eggs_size_avg /= total_eggs

else:
	eggs_size_avg = 100

if eggs_size_avg < 100:
	eggs_size_avg = 100


# Estimating how many eggs fits in each cluster...
for cluster in areas_clusters:
	total_eggs += np.round(float(len(cluster)) / float(eggs_size_avg))


print(IO.json_packing_success(int(total_eggs)))