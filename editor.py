import pygame
import math
import re
import json
from uuid import uuid4
from copy import deepcopy
from squaternion import Quaternion
from os import getcwd, listdir
from os.path import exists, isfile, join as pathjoin, getmtime as lastmodified
from subprocess import run

SIZE = [1200, 600]
WHITE = (255, 255, 255)
BLUE = (0, 0, 255)

JSON_EXTENSION = ".layout.json"
LAYOUT_EXTENSION = ".layout"
BACKUP_EXTENSION = ".layout.backup"
FILE_REGEX = re.compile(f"^(.+)({JSON_EXTENSION}|{LAYOUT_EXTENSION})$")

POLYCONVERTER = "PolyConverter.exe"
SUCCESS_CODE = 0
JSON_ERROR_CODE = 1
CONVERSION_ERROR_CODE = 2
FILE_ERROR_CODE = 3
GAMEPATH_ERROR_CODE = 4


def entertoexit():
	input("\nPress Enter to exit...")
	exit()


def centroid(vertexes):
	_x_list = [vertex[0] for vertex in vertexes]
	_y_list = [vertex[1] for vertex in vertexes]
	_len = len(vertexes)
	_x = sum(_x_list) / _len
	_y = sum(_y_list) / _len
	return [_x, _y]


def rotate(origin, point, angle):
	"""Rotate a point counterclockwise by a given angle around a given origin.
	The angle should be given in radians.
	"""
	angle = math.radians(angle)

	ox, oy = origin
	px, py = point

	qx = ox + math.cos(angle) * (px - ox) - math.sin(angle) * (py - oy)
	qy = oy + math.sin(angle) * (px - ox) + math.cos(angle) * (py - oy)
	return [qx, qy]


def save(shapes, anchors, layout):
	global jsonfile, layoutfile, backupfile
	print(f"Saving changes to {jsonfile}...")
	layout["m_CustomShapes"] = []

	for shape in shapes:
		q = Quaternion.from_euler(*shape.rotation, degrees=True)
		localpoints = []
		for point in shape.points:
			localpoints.append({"x": point[0], "y": point[1]})
		shapedict = {
			"m_Pos": shape.position,
			"m_Rot": {"x": q[1], "y": q[2], "z": q[3], "w": q[0]},
			"m_Scale": {"x": 1, "y": 1, "z": 1},
			"m_Dynamic": shape.dynamic,
			"m_CollidesWithRoad": shape.collides_with_road,
			"m_CollidesWithNodes": shape.collides_with_nodes,
			"m_Flipped": shape.flipped,
			"m_RotationDegrees": shape.rotation_degrees,
			"m_Mass": shape.mass,
			"m_Bounciness": shape.bounciness,
			"m_PinMotorStrength": shape.pin_motor_strength,
			"m_PinTargetVelocity": shape.pin_target_velocity,
			"m_Color": {"r": shape.color[0] / 255, "g": shape.color[1] / 255, "b": shape.color[2] / 255, "a": 1},
			"m_PointsLocalSpace": localpoints,
			"m_StaticPins": shape.static_pins,
			"m_DynamicAnchorGuids": shape.dynamic_anchors,
			"m_UndoGuid": None}
		layout["m_CustomShapes"].append(shapedict)

	layout["m_Anchors"] = anchors
	layout["m_Bridge"]["m_Anchors"] = anchors
	with open(jsonfile, 'w') as openfile:
		json.dump(layout, openfile)
	print(f"Applied changes to {jsonfile}!")
	print("Converting...")
	program = run(f"{POLYCONVERTER} {jsonfile}", capture_output=True)
	if program.returncode == SUCCESS_CODE:
		if program.stdout is None or len(program.stdout) < 6:
			print("No changes to apply.")
		else:
			if "backup" in str(program.stdout):
				print(f"Created backup {backupfile}")
			print(f"Applied changes to {layoutfile}!")
		print("Done!")
		entertoexit()
	elif program.returncode == FILE_ERROR_CODE:  # Failed to save?
		print(program.stdout)
	else:
		print(f"Unexpected error:\n{program.stdout}")


class Shape:
	def __init__(self, color, position, points, scale, rotation, static_pins,
	             dynamic, collides_with_road, collides_with_nodes, flipped, rotation_degrees,
	             mass, bounciness, pin_motor_strength, pin_target_velocity, dynamic_anchors):
		self.position = position
		self.hitbox = None
		self.points = []
		self.offset_points = []
		self.highlighted = False
		self.color = tuple(list(color)[:-1])
		self.fill_color = color
		self.scale = scale
		self.rotation = rotation
		self.static_pins = static_pins
		self.dynamic = dynamic
		self.collides_with_road = collides_with_road
		self.collides_with_nodes = collides_with_nodes
		self.flipped = flipped
		self.rotation_degrees = rotation_degrees
		self.mass = mass
		self.bounciness = bounciness
		self.pin_motor_strength = pin_motor_strength
		self.pin_target_velocity = pin_target_velocity
		self.dynamic_anchors = dynamic_anchors

		for point in points:
			self.points.append([point["x"] * scale["x"], point["y"] * scale["y"]])
		points = []
		center = centroid(self.points)
		for point in self.points:
			points.append(rotate(center, point, self.rotation[2]))
		self.points = points

	def render(self, camera, zoom):
		global DISPLAY, hitboxes, anchors
		self.offset_points = []
		# Translate points to camera location, zoom etc
		for point in self.points:
			self.offset_points.append([(point[0] + self.position["x"] + camera[0]) * zoom,
			                           -((point[1]) + self.position["y"] + camera[1]) * zoom])
		offset_points_pixels = [[int(n) for n in p] for p in self.offset_points]
		self.hitbox = pygame.draw.polygon(DISPLAY, self.fill_color, offset_points_pixels)

		# Draw static pins
		pins = []
		for pin in self.static_pins:
			pins.append([(pin["x"] + camera[0]) * zoom, -(pin["y"] + camera[1]) * zoom])
		for pin in pins:
			pygame.draw.ellipse(DISPLAY, (165, 42, 42),
			                    (int(c) for c in (pin[0] - zoom / 2, pin[1] - zoom / 2, zoom, zoom)))
		# Draw dynamic anchors
		for anchor_id in self.dynamic_anchors:
			for anchor in anchors:
				if anchor_id == anchor["m_Guid"]:
					# print(anchor)
					# print((anchor["m_Pos"]["x"]+camera[0])*zoom,(anchor["m_Pos"]["y"]+camera[1])*zoom)
					pygame.draw.rect(DISPLAY, (255, 255, 255), (int(c) for c in
					                 ((anchor["m_Pos"]["x"] + camera[0]) * zoom - zoom / 4,
					                  -(anchor["m_Pos"]["y"] + camera[1]) * zoom - zoom / 4,
					                  zoom / 2, int(zoom / 2))))
		if hitboxes:
			pygame.draw.rect(DISPLAY, (0, 255, 0), self.hitbox, 1)
		if self.highlighted:
			pygame.draw.polygon(DISPLAY, (255, 255, 0), offset_points_pixels, 1)
		# print(self.color)

	def highlight(self, status):
		self.highlighted = status
		# pygame.draw.rect(DISPLAY,(0,0,255),(self.offset_points[0][0],self.offset_points[0][1],20,20))


if __name__ != "__main__":
	exit()


if not exists(POLYCONVERTER):
	print(f"Error: Cannot find {POLYCONVERTER} in this folder")
	entertoexit()

program = run(f"{POLYCONVERTER} test", capture_output=True)
if program.returncode == GAMEPATH_ERROR_CODE:  # game install not found
	print(program.stdout)
	entertoexit()
elif program.returncode == FILE_ERROR_CODE:  # as "test" is not a valid file
	pass
else:  # .NET not installed?
	print("Unexpected error:\n")
	print(program.stdout)
	entertoexit()

currentdir = getcwd()
filelist = [f for f in listdir(currentdir) if isfile(pathjoin(currentdir, f))]
levellist = [match.group(1) for match in [FILE_REGEX.match(f) for f in filelist] if match]
levellist = list(dict.fromkeys(levellist))  # remove duplicates

leveltoedit = None

if len(levellist) == 0:
	print("There are no levels to edit in the current folder")
	entertoexit()
elif len(levellist) == 1:
	leveltoedit = levellist[0]
else:
	print("[#] Enter the number of the level you want to edit:")
	print("\n".join([f" ({i + 1}). {s}" for (i, s) in enumerate(levellist)]))
	while True:
		try:
			index = int(input())
		except ValueError:
			pass
		if 0 < index < len(levellist) + 1:
			leveltoedit = levellist[index - 1]
			break

layoutfile = leveltoedit + LAYOUT_EXTENSION
jsonfile = leveltoedit + JSON_EXTENSION
backupfile = leveltoedit + BACKUP_EXTENSION

if (layoutfile in filelist and
		(jsonfile not in filelist or lastmodified(layoutfile) > lastmodified(jsonfile))):
	program = run(f"{POLYCONVERTER} {layoutfile}", capture_output=True)
	if program.returncode == SUCCESS_CODE:
		if program.stdout is not None and len(program.stdout) >= 6:
			print(f"{'Created' if 'Created' in str(program.stdout) else 'Updated'} {jsonfile}!")
	else:
		print(f"Error: There was a problem converting {layoutfile}. Full output below:\n")
		print(program.stdout)
		entertoexit()

with open(jsonfile) as openfile:
	try:
		layout = json.load(openfile)
		_ = layout["m_CustomShapes"]
		_ = layout["m_Anchors"]
	except json.JSONDecodeError as error:
		print(f"Syntax error in line {error.lineno}, column {error.colno} of {jsonfile}")
		entertoexit()
	except ValueError:
		print(f"Error: {jsonfile} is either incomplete or not a valid level")
		entertoexit()

print("Layout Loaded Successfully!")

start_x, start_y = 0, 0
mouse_x, mouse_y = 0, 0
camera = [SIZE[0] / 2, -(SIZE[1] / 2)]
clock = pygame.time.Clock()
fps = 60
zoom = 1
hitboxes = False
dragging = False
selecting = False
custom_shapes = []
selected_shapes = []
anchors = deepcopy(layout["m_Anchors"])

for shape in layout["m_CustomShapes"]:
	q = Quaternion(shape["m_Rot"]["w"], shape["m_Rot"]["x"], shape["m_Rot"]["y"], shape["m_Rot"]["z"])
	q = q.to_euler(degrees=True)
	points = []
	color = []
	for item in list(shape["m_Color"].values()):
		color.append(item * 255)
	custom_shapes.append(
		Shape(color, shape["m_Pos"], shape["m_PointsLocalSpace"], shape["m_Scale"], q, shape["m_StaticPins"],
		      shape["m_Dynamic"], shape["m_CollidesWithRoad"], shape["m_CollidesWithNodes"], shape["m_Flipped"],
		      shape["m_RotationDegrees"], shape["m_Mass"], shape["m_Bounciness"], shape["m_PinMotorStrength"],
		      shape["m_PinTargetVelocity"], shape["m_DynamicAnchorGuids"]))

DISPLAY = pygame.display.set_mode(SIZE)
pygame.init()
pygame.draw.rect(DISPLAY, BLUE, (200, 150, 100, 50))
for shape in custom_shapes:
	shape.render(camera, zoom)
print()

done = False
while not done:
	for event in pygame.event.get():
		DISPLAY.fill((0, 0, 0))
		if event.type == pygame.QUIT:
			done = True
			pygame.quit()
			exit()
		elif event.type == pygame.MOUSEBUTTONDOWN:
			start_x, start_y = 0, 0
			if event.button == 1:
				dragging = True
				old_mouse_x, old_mouse_y = event.pos
				offset_x = 0
				offset_y = 0
			if event.button == 4:
				zoom += zoom * 0.1
			if event.button == 5:
				zoom += -(zoom * 0.1)
			if event.button == 3:
				start_x, start_y = event.pos
				mouse_x, mouse_y = event.pos
				selecting = True
				true_start = (mouse_x / zoom - camera[0]), (-mouse_y / zoom - camera[1])
		elif event.type == pygame.MOUSEBUTTONUP:
			if event.button == 1:
				dragging = False
			if event.button == 3:
				selecting = False
				start_x, start_y = 0, 0
		elif event.type == pygame.MOUSEMOTION:
			if dragging:
				mouse_x, mouse_y = event.pos
				camera[0] = camera[0] + (mouse_x - old_mouse_x) / zoom
				camera[1] = camera[1] - (mouse_y - old_mouse_y) / zoom
				old_mouse_x, old_mouse_y = mouse_x, mouse_y
			if selecting:
				mouse_x, mouse_y = event.pos
				# pygame.draw.rect(DISPLAY,(0,255,0),pygame.Rect(start_x,start_y,mouse_x-start_x,mouse_y-start_y),1)
		elif event.type == pygame.KEYDOWN:
			if event.key == ord('h'):
				hitboxes = not hitboxes
			if event.key == ord('d'):
				# delete selected
				for shape in custom_shapes[:]:
					if shape.highlighted:
						custom_shapes.remove(shape)
						shape.highlight(False)
			# Moving selection
			x_change, y_change = 0, 0
			move = False
			if event.key == pygame.K_LEFT:
				x_change = -1
				move = True
			if event.key == pygame.K_RIGHT:
				x_change = 1
				move = True
			if event.key == pygame.K_UP:
				y_change = 1
				move = True
			if event.key == pygame.K_DOWN:
				y_change = -1
				move = True

			if move:
				for shape in custom_shapes:
					if shape.highlighted:
						shape.position["x"] += x_change
						shape.position["y"] += y_change
						for c, pin in enumerate(shape.static_pins):
							shape.static_pins[c]["x"] += x_change
							shape.static_pins[c]["y"] += y_change

						for anchor_id in shape.dynamic_anchors:
							for c, anchor in enumerate(anchors[:]):
								if anchor["m_Guid"] == anchor_id:
									# print(shape.dynamic_anchors)
									anchors[c]["m_Pos"]["x"] += x_change
									anchors[c]["m_Pos"]["y"] += y_change
				move = False
			if event.key == ord("c"):
				# print("copy")
				for shape in custom_shapes:
					if shape.highlighted:
						old = deepcopy(shape)
						old.highlight(False)
						custom_shapes.append(old)
						current_shape_anchors = deepcopy(shape).dynamic_anchors
						duplicate_anchors = deepcopy(anchors)
						shape.dynamic_anchors = []
						for anchor_id in current_shape_anchors:
							for anchor in duplicate_anchors:
								# DOESNT WORK
								if anchor["m_Guid"] == anchor_id:
									# print(anchor)
									anchors.append(anchor)
									new_id = str(uuid4())
									anchors[len(anchors) - 1]["m_Guid"] = new_id
									shape.dynamic_anchors.append(new_id)

									print(len(shape.dynamic_anchors))
			if event.key == ord("s"):
				save(custom_shapes, anchors, layout)

	# Selecting shapes
	if selecting:
		# print(f"True mouse position: {(mouse_x/zoom-camera[0])},{(-mouse_y/zoom-camera[1])}")
		select_box = pygame.draw.rect(DISPLAY, (0, 255, 0),
		                              pygame.Rect(start_x, start_y, mouse_x - start_x, mouse_y - start_y), 1)
		true_current = (mouse_x / zoom - camera[0]), (-mouse_y / zoom - camera[1])
		# print(true_start,true_current)
		selected_shapes = []
		for shape in custom_shapes:

			if shape.hitbox.colliderect(select_box):
				# print(shape.position)
				shape.highlight(True)
			elif shape.highlighted:
				shape.highlight(False)

	# Render Shapes
	for shape in custom_shapes:
		shape.render(camera, zoom)
	# for shape in selected_shapes:
	# 	current = shape.render(camera,zoom)

	pygame.display.flip()
	clock.tick(fps)
