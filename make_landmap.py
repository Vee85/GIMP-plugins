#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  make_landmap.py
#  
#  Copyright 2018 Valentino Esposito <valentinoe85@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  

#This script generate or edit a regional map, can be used to generate gdr-like maps. It follows a tutorial on http://www.cartographersguild.com/
#IT IS NOT YET COMPLETED
#This script must be placed in ~/.gimp-n.m/plug-ins
#where n.m is the gimp version (e.g. 2.8)

#@@@ add some choice on options island (radius) e single coast (direction of the coast and amount of land)

import sys
import os
import math
import random
import gtk
import gobject
from gimpfu import *

FSG = 10


#generic function used to adjust RGB color of a color gobject
def gdkcoltorgb(gdkc):
  red = int(gdkc.red_float * 255)
  green = int(gdkc.green_float * 255)
  blue = int(gdkc.blue_float * 255)
  return (red, green, blue)

#generic function to fill a layer with a color
def colfillayer(image, layer, rgbcolor):
  oldfgcol = pdb.gimp_context_get_foreground()
  pdb.gimp_context_set_foreground(rgbcolor) #set foreground color
  pdb.gimp_edit_bucket_fill(layer, 0, 0, 100, 255, True, pdb.gimp_image_width(image)/2, pdb.gimp_image_height(image)/2) #0 (first): filling the layer with foreground color
  pdb.gimp_context_set_foreground(oldfgcol)


#class to adjust the color levels/threshold of a layer, reproducing a simpler interface to the GIMP color levels dialog or the GIMP color threshold dialog. 
class CLevDialog(gtk.Dialog):
  #class constants (used as a sort of enumeration)
  LEVELS = 0
  THRESHOLD = 1
  
  GAMMA = 0
  INPUT_MIN = 1
  INPUT_MAX = 2
  OUTPUT_MIN = 3
  OUTPUT_MAX = 4
  LEV_ALL = 5
  
  THR_MIN = 0
  THR_MAX = 1
  THR_ALL = 2

  #constructor
  def __init__(self, image, layer, ltext, ctype, modes, *args):
    dwin = gtk.Dialog.__init__(self, *args)
    self.set_border_width(10)
    self.connect("destroy", gtk.main_quit)

    #internal arguments
    self.ctype = ctype
    self.modes = modes
    self.img = image
    self.origlayer = layer
    self.reslayer = None
    self.lapos = [j for i, j in zip(self.img.layers, range(len(self.img.layers))) if i.name == self.origlayer.name][0]
    self.inlow = 0 #threshold color set to minimum (if used in the three channel (RGB) is black)
    self.inhigh = 255 #threshold color set to maximum (if used in the three channel (RGB) is white)
    self.gamma = 1.0 #gamma value for input color
    self.outlow = 0 #threshold color set to minimum (if used in the three channel (RGB) is black)
    self.outhigh = 255 #threshold color set to maximum (if used in the three channel (RGB) is white)
    self.thrmin = 127 #threshold color set to middle 
    self.thrmax = 255 #threshold color set to max
    
    if self.ctype != CLevDialog.LEVELS and self.ctype != CLevDialog.THRESHOLD:
      sys.stderr.write("Error, ctype value not allowed")
      sys.stderr.flush()
      return
    
    #Designing the interface
    #new row
    laba = gtk.Label(ltext)
    self.vbox.add(laba)

    labtxt = []
    adjlist = []
    hboxes = []
    labb = []
    scab = []
    spbutc = []
    
    if self.ctype == CLevDialog.LEVELS:
      if self.modes[0] == CLevDialog.LEV_ALL:
        self.modes = [CLevDialog.GAMMA, CLevDialog.INPUT_MIN, CLevDialog.INPUT_MAX, CLevDialog.OUTPUT_MIN, CLevDialog.OUTPUT_MAX]
    elif self.ctype == CLevDialog.THRESHOLD:
      if self.modes[0] == CLevDialog.THR_ALL:
        self.modes = [CLevDialog.THR_MIN, CLevDialog.THR_MAX]
    
    #creating the necessary adjustments
    if self.ctype == CLevDialog.LEVELS:
      for m in self.modes:
        if (m == CLevDialog.GAMMA):
          adjlist.append(gtk.Adjustment(self.gamma, 0.10, 10.00, 0.01, 0.1))
          labtxt.append("Gamma")
        if (m == CLevDialog.INPUT_MIN):
          adjlist.append(gtk.Adjustment(self.inlow, 0, 255, 1, 10))
          labtxt.append("Low Input")
        if (m == CLevDialog.INPUT_MAX):
          adjlist.append(gtk.Adjustment(self.inhigh, 0, 255, 1, 10))
          labtxt.append("High Input")
        if (m == CLevDialog.OUTPUT_MIN):
          adjlist.append(gtk.Adjustment(self.outlow, 0, 255, 1, 10))
          labtxt.append("Low Output")
        if (m == CLevDialog.OUTPUT_MAX):
          adjlist.append(gtk.Adjustment(self.outhigh, 0, 255, 1, 10))
          labtxt.append("High Output")
    elif self.ctype == CLevDialog.THRESHOLD:
      for m in self.modes:
        if (m == CLevDialog.THR_MIN):
          adjlist.append(gtk.Adjustment(self.thrmin, 0, 255, 1, 10))
          labtxt.append("Min Threshold")
        if (m == CLevDialog.THR_MAX):
          adjlist.append(gtk.Adjustment(self.thrmax, 0, 255, 1, 10))
          labtxt.append("Max Threshold")
          
    #making the scale and spinbuttons for the adjustments
    for adj, ww, lt in zip(adjlist, self.modes, labtxt):
      #new row
      hboxes.append(gtk.HBox(spacing=10, homogeneous=False))
      self.vbox.add(hboxes[-1])
    
      labb.append(gtk.Label(lt))
      hboxes[-1].add(labb[-1])
      
      scab.append(gtk.HScale(adj))
      scab[-1].connect("value-changed", self.on_value_changed, ww)
      hboxes[-1].add(scab[-1])
      
      spbutc.append(gtk.SpinButton(adj, 0, 2))
      spbutc[-1].connect("output", self.on_value_changed, ww)
      hboxes[-1].add(spbutc[-1])
      
    #action area
    butok = gtk.Button("OK")
    self.action_area.add(butok)
    butok.connect("clicked", self.on_butok_clicked)
    
    self.show_all()
    return dwin

  #method, create the result layer
  def make_reslayer(self):
    #deleting the reslayer and recreating if it already exists
    if self.reslayer is not None:
      pdb.gimp_image_remove_layer(self.img, self.reslayer)
    
    pdb.gimp_item_set_visible(self.origlayer, True)
    self.reslayer = self.origlayer.copy()
    self.img.add_layer(self.reslayer, self.lapos)
    pdb.gimp_item_set_visible(self.origlayer, False)
  
  #callback method, apply the new value
  def on_value_changed(self, widget, m):
    self.make_reslayer()

    if self.ctype == CLevDialog.LEVELS:
      if (m == CLevDialog.GAMMA):
        self.gamma = widget.get_value()
      if (m == CLevDialog.INPUT_MIN):
        self.inlow = widget.get_value()
      if (m == CLevDialog.INPUT_MAX):
        self.inhigh = widget.get_value()
      if (m == CLevDialog.OUTPUT_MIN):
        self.outlow = widget.get_value()
      if (m == CLevDialog.OUTPUT_MAX):
        self.outhigh = widget.get_value()
            
      pdb.gimp_levels(self.reslayer, 0, self.inlow, self.inhigh, self.gamma, self.outlow, self.outhigh) #regulating color levels, channel = #0 (second parameter) is for histogram value

    elif self.ctype == CLevDialog.THRESHOLD:
      if (m == CLevDialog.THR_MIN):
        self.thrmin = widget.get_value()
      if (m == CLevDialog.THR_MAX):
        self.thrmax = widget.get_value()
      
      pdb.gimp_threshold(self.reslayer, self.thrmin, self.thrmax) #regulating threshold levels
    
    pdb.gimp_displays_flush()

  #callback method for ok button
  def on_butok_clicked(self, widget):
    rname = self.origlayer.name
    pdb.gimp_image_remove_layer(self.img, self.origlayer)
    self.reslayer.name = rname
    self.hide()
    

#class linked to a graphic marker in the drawing area
class CCMarker:
  #constructor
  def __init__(self, x, y, at=True):
    self.setcoord(x, y)
    self.setactive(at)

  #method, setting the coordinate
  def setcoord(self, x, y):
    self.x = x
    self.y = y

  #method, getting the x coordinate
  def getx(self):
    return self.x

  #method, getting the y coordinate
  def gety(self):
    return self.y

  #method, setting if active
  def setactive(self, at):
    self.active = at

  #method, getting if active
  def getactive(self):
    return self.active
  
  #method, get distance from coordinates
  def cdistance(self, cx, cy):
    dx = self.x - cx
    dy = self.y - cy
    return math.sqrt(dx*dx + dy*dy)


#class to adjust the color levels of a layer, reproducing a simpler interface to the GIMP color curves dialog. 
class BDrawDial(gtk.Dialog):
  #constructor
  def __init__(self, ltext, *args):
    dwin = gtk.Dialog.__init__(self, *args)
    self.set_border_width(10)
    self.connect("destroy", gtk.main_quit)

    #internal argument
    self.drw = 500
    self.drh = 500
    self.xfr = 10
    self.yfr = 10
    self.radmar = 5
    self.redrawrad = self.radmar + 2
    self.markers = []
    self.draggedmarker = None

    #Designing the interface
    #new row
    ditext = "Histogram in log scale of the pixel counts.\n"
    ditext += "Click to add a control point, or draw one to another position.\n"
    laba = gtk.Label(ditext + ltext)
    self.vbox.add(laba)
    
    #the drawing area
    self.darea = gtk.DrawingArea()
    self.darea.set_size_request(self.drw, self.drh)
    self.darea.connect("expose-event", self.on_expose)
    self.darea.add_events(gtk.gdk.BUTTON_PRESS_MASK)
    self.darea.add_events(gtk.gdk.BUTTON_RELEASE_MASK)
    #~ self.darea.add_events(gtk.gdk.POINTER_MOTION_MASK)
    self.darea.connect("button-press-event", self.on_button_press)
    self.darea.connect("button-release-event", self.on_button_release)
    #~ self.darea.connect("motion-notify-event", self.on_pointer_moving)
    self.vbox.add(self.darea)

    #action area empty

    self.show_all()
    return dwin

  #callback method, draw stuffs when the drawing area appears
  def on_expose(self, widget, ev):
    cr = widget.window.cairo_create()
    cr.set_line_width(2)
    cr.set_source_rgb(0.5, 0.5, 0.5)
    cr.move_to(0, self.drh)
    cr.line_to(self.drw, 0)
    
    cr.stroke()

    if len(self.markers) > 0:
      for i in self.markers:
        self.drawmarker(i)

  #method, sort markers on their x coordinate
  def sortmarkers(self):
    self.markers.sort(key= lambda o: o.getx())

  #method, draw a marker
  def drawmarker(self, mm):
    cr = self.darea.window.cairo_create()
    cr.set_line_width(1)
    cr.set_source_rgb(0, 0, 0)
    cr.arc(mm.getx(), mm.gety(), self.radmar, 0, 2*math.pi)
    if mm.getactive():
      cr.fill()

    cr.stroke()

  #method, verify distances and get the marker, if any
  def markdist(self, x, y):
    res = None
    for m in self.markers:
      if m.cdistance(x, y) <= self.radmar:
        res = m
        break

    return res

  #callback method, draw a circle on button press or set for redraw
  def on_button_press(self, widget, ev):
    if ev.type == gtk.gdk.BUTTON_PRESS:
      closemarker = self.markdist(ev.x, ev.y)
      if closemarker is None:
        if ev.button == 1:
          att = True
        elif ev.button == 3:
          att = False

        mm = CCMarker(ev.x, ev.y, att)
        self.markers.append(mm)
        self.sortmarkers()
        self.drawmarker(mm)

      else:
        self.draggedmarker = closemarker

  #callback method, redraw a circle on button release
  def on_button_release(self, widget, ev):
    if ev.type == gtk.gdk.BUTTON_RELEASE:
      if self.draggedmarker is not None:
        if self.draggedmarker.cdistance(ev.x, ev.y) <= self.radmar:
          self.draggedmarker.setactive(not self.draggedmarker.getactive())
          widget.queue_draw_area(int(self.draggedmarker.getx() - self.redrawrad), int(self.draggedmarker.gety() - self.redrawrad), self.redrawrad*2, self.redrawrad*2)
        else:
          oldx = self.draggedmarker.getx()
          oldy = self.draggedmarker.gety()
          self.draggedmarker.setcoord(ev.x, ev.y)
          self.sortmarkers()
          widget.queue_draw_area(int(oldx - self.redrawrad), int(oldy - self.redrawrad), self.redrawrad*2, self.redrawrad*2)
          widget.queue_draw_area(int(self.draggedmarker.getx() - self.redrawrad), int(self.draggedmarker.gety() - self.redrawrad), self.redrawrad*2, self.redrawrad*2)
        
        self.draggedmarker = None
        

#class to adjust the color levels of a layer, reproducing a simpler interface to the GIMP color curves dialog. 
class CCurveDialog(BDrawDial):
  #constructor
  def __init__(self, image, layer, ltext, *args):
    dwin = BDrawDial.__init__(self, ltext, *args)

    #internal arguments
    self.img = image
    self.origlayer = layer
    self.reslayer = None
    self.cns = None
    self.lapos = [j for i, j in zip(self.img.layers, range(len(self.img.layers))) if i.name == self.origlayer.name][0]
    
    #action area
    self.butrest = gtk.Button("Restore")
    self.action_area.add(self.butrest)
    self.butrest.connect("clicked", self.on_butrest_clicked, True)
    
    self.butprev = gtk.Button("See preview")
    self.action_area.add(self.butprev)
    self.butprev.connect("clicked", self.on_butprev_clicked)
    
    self.butok = gtk.Button("OK")
    self.action_area.add(self.butok)
    self.butok.connect("clicked", self.on_butok_clicked)
    
    self.show_all()
    self.getcounts()
    self.xunit = (self.drw - 2*self.xfr) / 255.0
    self.yunit = (self.drh - 2*self.yfr) / 255.0
    
    #here adding some basic markers to control the curve
    self.on_butrest_clicked(self.butrest, False)
    
    self.show_all()
    return dwin

  #method to get the counts in the pixel histogram
  def getcounts(self):
    fullres = [pdb.gimp_histogram(self.origlayer, 0, i, i) for i in range(255)]
    self.cns = [(j, math.log(i[4]) if i[4] != 0 else -1) for i, j in zip(fullres, range(len(fullres)))]

  #method to convert a marker coordinate from pixel to color scale unit (0 - 255) 
  def markerconvert(self, mm):
    mx = (mm.getx() - self.xfr) / self.xunit
    my = 255.0 - ((mm.gety() - self.yfr) / self.yunit)
    #~ print "markerconvert", mx, my
    #~ sys.stdout.flush()
    return mx, my

  #method, create the result layer
  def make_reslayer(self):
    #deleting the reslayer and recreating if it already exists
    if self.reslayer is not None:
      pdb.gimp_image_remove_layer(self.img, self.reslayer)
    
    pdb.gimp_item_set_visible(self.origlayer, True)
    self.reslayer = self.origlayer.copy()
    self.img.add_layer(self.reslayer, self.lapos)
    pdb.gimp_item_set_visible(self.origlayer, False)

  #callback method, draw stuffs when the drawing area appears
  def on_expose(self, widget, ev):
    if self.cns is not None:
      #drawing boundaries
      cr = widget.window.cairo_create()
      cr.set_source_rgb(0, 0, 0)
      cr.set_line_width(2)
      #top line
      cr.move_to(0, self.yfr)
      cr.line_to(self.drw, self.yfr)
      #botton line
      cr.move_to(0, self.drh - self.yfr)
      cr.line_to(self.drw, self.drh - self.yfr)
      #left line
      cr.move_to(self.xfr, 0)
      cr.line_to(self.xfr, self.drh)
      #right line
      cr.move_to(self.drw - self.xfr, 0)
      cr.line_to(self.drw - self.xfr, self.drh)

      #drawing histogram
      cr.set_source_rgb(0.3, 0.3, 0.3)
      cr.set_line_width(1)
      
      xscale = 1.0*(self.drw - 2*self.xfr) / len(self.cns)
      yscale = (self.drh - 2*self.yfr) / max([i[1] for i in self.cns])
      
      #here drawing the log histogram on the background
      for i in self.cns:
        cr.move_to(self.xfr + i[0]*xscale, self.drh - self.yfr)
        cr.line_to(self.xfr + i[0]*xscale, self.drh - self.yfr - i[1]*yscale)
      
      cr.stroke()
      
      BDrawDial.on_expose(self, widget, ev)
      
  #callback method, replace all markers with default
  def on_butrest_clicked(self, widget, doprev=True):
    self.markers = [CCMarker(self.xfr, self.drh - self.yfr, True), CCMarker(self.drw - self.xfr, self.yfr, True)]
    if doprev:
      self.on_butprev_clicked(self.butprev)
  
  #callback method, show preview
  def on_butprev_clicked(self, widget):
    self.make_reslayer()
    actmarks = [m for m in self.markers if m.getactive()]
    self.markers = actmarks
    ctrlptem = [self.markerconvert(m) for m in self.markers]
    ctrlp = list(sum(ctrlptem, ())) #this flatten the list of tuples
    corrctrlp = [i if i >= 0 and i <= 255 else 0 if i < 0 else 255 for i in ctrlp] #ensuring that there are not values outside allowed range
    pdb.gimp_curves_spline(self.reslayer, 0, len(corrctrlp), corrctrlp) #0 (second) = editing histogram value.
    pdb.gimp_displays_flush()

  #callback method, accept the preview
  def on_butok_clicked(self, widget):
    if self.reslayer is not None:
      rname = self.origlayer.name
      pdb.gimp_image_remove_layer(self.img, self.origlayer)
      self.reslayer.name = rname
      pdb.gimp_displays_flush()
      self.hide()
    

#base class to implement the TSL tecnnique. This class is inherited by the GUI-provided classes.
#it works as a sort of abstract class, but python does not have the concecpt of abstract classes, so it's just a normal class. 
class TLSbase(gtk.Dialog):
  #constructor
  def __init__(self, image, drawable, basemask, layermask, channelmask, *args):
    mwin = gtk.Dialog.__init__(self, *args)
    self.set_border_width(10)
    
    #Obey the window manager quit signal:
    self.connect("destroy", gtk.main_quit)
    
    #internal arguments
    self.img = image
    self.bgl = drawable
    self.noisel = None
    self.clipl = None
    self.baseml = basemask
    self.maskl = layermask
    self.channelms = channelmask
    self.thrc = 0 #will be selected later
    
    #nothing in the dialog: labels and buttons are created in the child classes
    
    return mwin
    
  #method to close the dialog at the end
  def on_job_done(self):
    pdb.gimp_displays_flush()
    self.hide()
      
  #method to get the maximum brightness from the pixel histogram of a layer
  def get_brightness_max(self, layer, channel=HISTOGRAM_VALUE):
    endr = 255
    found = False
    while not found:
      mean, std_dev, median, pixels, count, percentile = pdb.gimp_histogram(layer, channel, 0, endr)
      if (count < pixels):
        found = True
      else:
        endr = endr - 1
        
    return endr
    
  #method to get the minimum brightness from the pixel histogram of a layer
  def get_brightness_min(self, layer, channel=HISTOGRAM_VALUE):
    startr = 0
    found = False
    while not found:
      mean, std_dev, median, pixels, count, percentile = pdb.gimp_histogram(layer, channel, startr, 255)
      if (count < pixels):
        found = True
      else:
        startr = startr + 1
        
    return startr
  
  #method to generate a uniformly colored layer (typically the background layer
  def makeunilayer(self, lname, lcolor=None):
    res = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, lname, 100, 0) #0 = normal mode
    self.img.add_layer(res, 0)
    if lcolor is None:      
      lcolor = (255, 255, 255) #make layer color white
    
    colfillayer(self.img, res, lcolor)
    pdb.gimp_displays_flush()
    return res
  
  #method to generate the uniformly colored background layer
  def makebgl(self, lcolor=None):
    self.bgl = self.makeunilayer("bgl", lcolor)

  #method to generate the noise layer
  def makenoisel(self, lname, pixsize, mode=NORMAL_MODE, turbulent=False):    
    noiselayer = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, lname, 100, mode)
    self.img.add_layer(noiselayer, 0)
    pdb.plug_in_solid_noise(self.img, noiselayer, False, turbulent, random.random() * 9999999999, 15, pixsize, pixsize)
    return noiselayer
  
  #method to generate the clip layer
  def makeclipl(self, lname, commtxt):
    cliplayer = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, lname, 100, 10) #10 = lighten only mode
    self.img.add_layer(cliplayer, 0)
    colfillayer(self.img, cliplayer, (255, 255, 255)) #make layer color white
    
    cld = CLevDialog(self.img, cliplayer, commtxt, CLevDialog.LEVELS, [CLevDialog.OUTPUT_MAX], "Set clip layer level", self, gtk.DIALOG_MODAL) #title = "sel clip...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    cld.run()
    cliplayer = cld.reslayer
    self.thrc = cld.outhigh
    cld.destroy()
    return cliplayer

  #method to merge two layer representing two masks
  def mergemasks(self):
    if self.baseml is not None and self.maskl is not None:
      mlpos = [j for i, j in zip(self.img.layers, range(len(self.img.layers))) if i.name == self.maskl.name][0]
      copybl = self.baseml.copy()
      self.img.add_layer(copybl, mlpos)
      pdb.gimp_layer_set_mode(copybl, DARKEN_ONLY_MODE)
      self.maskl = pdb.gimp_image_merge_down(self.img, copybl, 0)

  #method to make the final layer with the profile and save it in a channel.
  #remember: white = transparent, black = blocked
  def makeprofilel(self, lname):
    pdb.gimp_context_set_sample_merged(True)
    pdb.gimp_image_select_color(self.img, 2, self.clipl, (int(self.thrc), int(self.thrc), int(self.thrc))) #2 = selection replace
    pdb.gimp_context_set_sample_merged(False)
    pdb.gimp_selection_invert(self.img) #inverting selection
    self.maskl = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, lname, 100, 0) #0 (last) = normal mode
    self.img.add_layer(self.maskl, 0)
    colfillayer(self.img, self.maskl, (255, 255, 255)) #make layer color white
    
    #merging the mask with a previous mask
    if self.baseml is not None:
      pdb.gimp_selection_none(self.img)
      self.mergemasks()
      pdb.gimp_image_select_color(self.img, 2, self.maskl, (255, 255, 255)) #2 = selection replace
    
    self.channelms = pdb.gimp_selection_save(self.img)
    pdb.gimp_selection_none(self.img)
    
  #method to apply a channel mask to a layer 
  def addmaskp(self, layer, inverting=False, applying=False):
    if pdb.gimp_layer_get_mask(layer) is None:
      maskmode = 0 #white mask (full transparent)
      if (self.channelms is not None):
        maskmode = 6 #channel mask
        if (pdb.gimp_image_get_active_channel(self.img) is None): #checking if there is already an active channel
          pdb.gimp_image_set_active_channel(self.img, self.channelms) #setting the active channel: if there is no active channel, gimp_layer_create_mask will fail.
      
      mask = pdb.gimp_layer_create_mask(layer, maskmode)
      pdb.gimp_layer_add_mask(layer, mask)

      if (inverting):
        pdb.gimp_invert(mask)
    
    else:
      #mask already present, hence it is removed with the MASK_APPLY option
      applying = True
        
    if (applying):
      pdb.gimp_layer_remove_mask(layer, 0) #0 = MASK_APPLY
      return None
    else:
      return mask
  
  #method to apply a color gradient map to a layer (layer colors are scaled through the gradient)
  def cgradmap(self, layer, darkc, lightc):
    oldfgcol = pdb.gimp_context_get_foreground()
    pdb.gimp_context_set_foreground(darkc) #set foreground color
    oldbgcol = pdb.gimp_context_get_background()
    pdb.gimp_context_set_background(lightc) #set background color
    
    #command to make the gradient map
    pdb.gimp_context_set_gradient('Da pp a sf (RGB)')
    pdb.plug_in_gradmap(self.img, layer)
    
    pdb.gimp_context_set_foreground(oldfgcol)
    pdb.gimp_context_set_background(oldbgcol)


#class to generate random land profile
class MaskProfile(TLSbase):
  #constructor
  def __init__(self, textes, image, tdraw, basemask, *args):
    mwin = TLSbase.__init__(self, image, tdraw, basemask, None, None, *args)
    
    #internal arguments
    self.textes = textes
    self.genonce = False
    self.namelist = self.textes["namelist"]
    self.typelist = range(len(self.namelist))
    self.chtype = 0 #will be reinitialized in GUI costruction
    
    #new row
    labb = gtk.Label(self.textes["toplab"])
    self.vbox.add(labb)
    
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Select type")
    hbxa.add(laba)
    
    boxmodela = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT)
    
    #filling the model for the combobox
    for i, j in zip(self.namelist, self.typelist):
      irow = boxmodela.append(None, [i, j])

    self.chtype = self.typelist[0]

    cboxa = gtk.ComboBox(boxmodela)
    rendtexta = gtk.CellRendererText()
    cboxa.pack_start(rendtexta, True)
    cboxa.add_attribute(rendtexta, "text", 0)
    cboxa.set_entry_text_column(0)
    cboxa.set_active(0)
    cboxa.connect("changed", self.on_type_changed)
    hbxa.add(cboxa)
    
    #new row
    blab = "To generate a more elaborate profile, draw a gradient with the shape you wish\n"
    blab += "and select the customized option in the dropdown menu.\n"
    blab += "Press again Generate land profile if you want to regenerate the profile.\n"
    blab += "Press Next step to continue." 
    labc = gtk.Label(blab)
    self.vbox.add(labc)
    
    #button area
    butgenpr = gtk.Button("Generate profile")
    self.action_area.add(butgenpr)
    butgenpr.connect("clicked", self.on_butgenpr_clicked)
    
    butnext = gtk.Button("Next step")
    self.action_area.add(butnext)
    butnext.connect("clicked", self.on_butnext_clicked)
    
    self.show_all()
    return mwin
  
  #callback method, setting the coast type to the one in the combobox
  def on_type_changed(self, widget):
    refmode = widget.get_model()
    self.chtype = refmode.get_value(widget.get_active_iter(), 1)
  
  #callback method, regenerate the land profile
  def on_butnext_clicked(self, widget):
    if not self.genonce:
      if (self.chtype == 0):
        self.on_job_done()
      else:
        #dialog telling to press the other button first
        infodi = gtk.Dialog(title="Warning", parent=self)
        ilabel = gtk.Label("You cannot go to the next step until you generate a profile.\nPress the \"Generate profile\" button first.")
        infodi.vbox.add(ilabel)
        ilabel.show()
        infodi.add_button("Ok", gtk.RESPONSE_OK)
        infodi.run()
        infodi.destroy()
        
    else:
      self.on_job_done()
  
  #callback method, generate the profile
  def on_butgenpr_clicked(self, widget):
    #removing previous layers if we are regenerating
    if (self.genonce):
      if self.bgl is not None:
        pdb.gimp_image_remove_layer(self.img, self.bgl)
        self.bgl = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, "Sfondo", 100, 0) #0 = normal mode
        self.img.add_layer(self.bgl, 0)
        colfillayer(self.img, self.bgl, (255, 255, 255)) #make layer full white
      if self.noisel is not None:
        pdb.gimp_image_remove_layer(self.img, self.noisel)
      if self.clipl is not None:
        pdb.gimp_image_remove_layer(self.img, self.clipl)
      if self.maskl is not None:
        pdb.gimp_image_remove_layer(self.img, self.maskl)
      if self.channelms is not None:
        pdb.gimp_image_remove_channel(self.img, self.channelms)
      
    #Using the TSL tecnnique: shape layer
    if (self.chtype == 0): #no need of a coast, skip everything
      self.genonce = True
    else:
      if (self.chtype == 1): #to generate archipelago
        #setting the layer to a light gray color
        colfillayer(self.img, self.bgl, (128, 128, 128)) #rgb notation for a 50% gray
      elif (self.chtype > 1 and self.chtype < 5):
        if (self.chtype == 2): #to generate a coastline
          gradtype = 0 #linear
          x1 = random.random() * (pdb.gimp_image_width(self.img) / FSG)
          y1 = random.random() * (pdb.gimp_image_height(self.img) / FSG)
          x2 = pdb.gimp_image_width(self.img) - (random.random() * (pdb.gimp_image_width(self.img) / FSG))
          y2 = pdb.gimp_image_height(self.img) - (random.random() * (pdb.gimp_image_height(self.img) / FSG))
        elif (self.chtype == 3 or self.chtype == 4): #to generate a circular island or lake
          gradtype = 2 #radial
          x1 = pdb.gimp_image_width(self.img)/2
          y1 = pdb.gimp_image_height(self.img)/2
          aver = (x1 + y1)/2.0
          x2 = aver + (aver * (0.75 + random.random()/2.0))
          y2 = y1
        
        #drawing the gradients
        pdb.gimp_edit_blend(self.bgl, 0, 0, gradtype, 100, 0, 0, False, False, 1, 0, True, x1, y1, x2, y2) #0 (first) = normal mode, 0 (second) linear gradient
        if (self.chtype == 3): #inverting the gradient
          pdb.gimp_invert(self.bgl)
        
      elif (self.chtype == 5): #custom shape (gradient already present), nothing to do
        pass
      
      #making the other steps
      self.noisel = self.makenoisel(self.textes["baseln"] + "noise", 5, OVERLAY_MODE)
      cmm = "The lower the selected value, the wider the affected area."
      self.clipl = self.makeclipl(self.textes["baseln"] + "clip", cmm)
      self.makeprofilel(self.textes["baseln"] + "layer")
      self.genonce = True
      
      pdb.gimp_displays_flush()


#class to generate the water mass profile (sea, ocean, lakes)
class WaterProfile(TLSbase):
  #constructor
  def __init__(self, image, tdraw, layermask, channelmask, *args):
    mwin = TLSbase.__init__(self, image, tdraw, None, layermask, channelmask, *args)
    self.seal = None
    self.shorel = None

    #internal parameters
    self.smoothnamelist = ["none", "small", "medium", "large"]
    self.smoothtypelist = [0, 20, 40, 60] #is a percentage
    self.smooth = 0 #will be reinitialized in GUI costruction
    self.addshore = True
    
    self.colorwaterdeep = (37, 50, 95) #a deep blue color
    self.colorwaterlight = (241, 244, 253) #a very light blue color almost white
    
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Smoothing parameter for water deepness")
    hbxa.add(laba)
    
    boxmodela = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT)
    #filling the model for the combobox
    for i, j in zip(self.smoothnamelist, self.smoothtypelist):
      irow = boxmodela.append(None, [i, j])

    self.smooth = self.smoothtypelist[1]

    cboxa = gtk.ComboBox(boxmodela)
    rendtexta = gtk.CellRendererText()
    cboxa.pack_start(rendtexta, True)
    cboxa.add_attribute(rendtexta, "text", 0)
    cboxa.set_entry_text_column(0)
    cboxa.set_active(1)
    cboxa.connect("changed", self.on_smooth_type_changed)
    hbxa.add(cboxa)
    
    #new row
    hbxb = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxb)
    
    chbb = gtk.CheckButton("Add shore effect")
    chbb.set_active(self.addshore)
    chbb.connect("toggled", self.on_chb_toggled)
    hbxb.add(chbb)

    #button area
    butcanc = gtk.Button("Cancel")
    self.action_area.add(butcanc)
    butcanc.connect("clicked", gtk.main_quit)
    
    butgenpr = gtk.Button("Generate water profile")
    self.action_area.add(butgenpr)
    butgenpr.connect("clicked", self.on_butgenpr_clicked)

    self.show_all()
    return mwin
    
  #callback method, setting smooth parameter
  def on_smooth_type_changed(self, widget):
    refmode = widget.get_model()
    self.smooth = refmode.get_value(widget.get_active_iter(), 1)
  
  #callback method, setting shore parameter
  def on_chb_toggled(self, widget):
    self.addshore = widget.get_active()
  
  #callback method, generate water profile
  def on_butgenpr_clicked(self, widget):
    if (self.smooth > 0):
      pix = (self.smooth / 100.0) * ((self.img.width + self.img.height) / 2.0)
      pdb.plug_in_gauss(self.img, self.bgl, pix, pix, 0)
      pdb.gimp_displays_flush()
    
    self.noisel = self.makenoisel("seanoise", 4, OVERLAY_MODE)
    self.bgl = pdb.gimp_image_merge_down(self.img, self.noisel, 0)

    #copy noise layer into a new layer 
    self.seal = self.bgl.copy()
    self.seal.name = "sea"
    self.img.add_layer(self.seal, 0)
    
    self.addmaskp(self.seal, True, True)
    pdb.plug_in_normalize(self.img, self.seal)
    pdb.gimp_image_select_item(self.img, 2, self.seal) #this selects the transparent region of the layer, #2 = replace selection
    pdb.gimp_selection_invert(self.img) #inverting the selection
    colfillayer(self.img, self.seal, (255, 255, 255)) #filling selected area with white
    pdb.gimp_selection_none(self.img)

    #smoothing near the coast and apply color
    pdb.plug_in_gauss(self.img, self.seal, 20, 20, 0)
    self.cgradmap(self.seal, self.colorwaterdeep, self.colorwaterlight)
    
    #adding shore
    if (self.addshore):
      self.shorel = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, "seashore", 100, 0) #0 (last) = normal mode
      self.img.add_layer(self.shorel, 0)
      colfillayer(self.img, self.shorel, self.colorwaterlight)
      maskshore = self.addmaskp(self.shorel, False, False)
      pxpar = 0.01 * (self.img.width + self.img.height)/2.0
      if (pxpar < 5):
        pxpar = 5.0
      
      pdb.plug_in_gauss(self.img, maskshore, pxpar, pxpar, 0)
    
    self.on_job_done()


#class to generate the base land (color and mask of the terrain)
class BaseDetails(TLSbase):
  #constructor
  def __init__(self, image, tdraw, layermask, channelmask, *args):
    mwin = TLSbase.__init__(self, image, tdraw, None, layermask, channelmask, *args)
    self.bumpmapl = None
    self.basebumpsl = None
    
    #internal parameters
    #@@@ ideally all of these: grassland, desert, arctic, underdark || these should be smaller regions rendered in other ways: forest, mountain, swamp, coast 
    self.regionlist = ["grassland", "desert", "arctic"]
    self.regiontype = ["grass", "sand", "ice"]
    self.region = self.regiontype[0] #will be reinitialized in GUI costruction

    #~ self.desertlist = ["no", "manually", "randomly"]
    #~ self.deserttype = range(len(self.desertlist))
    #~ self.desertdo = 0 #will be reinitialized in GUI costruction
    
    #color couples to generate gradients
    self.colorgrassdeep = (76, 83, 41) #a dark green color, known as ditch
    self.colorgrasslight = (149, 149, 89) #a light green color, known as high grass
    self.colordesertdeep = (150, 113, 23) #a relatively dark brown, known as sand dune
    self.colordesertlight = (244, 164, 96) #a light brown almost yellow, known as sandy brown
    self.colorarcticdeep = (128, 236, 217) #a clear blue
    self.colorarcticlight = (232, 232, 232) #a dirty white
    
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Select type of region")
    hbxa.add(laba)
    
    boxmodela = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
    #filling the model for the combobox
    for i, j in zip(self.regionlist, self.regiontype):
      irow = boxmodela.append(None, [i, j])

    self.region = self.regiontype[0]

    cboxa = gtk.ComboBox(boxmodela)
    rendtexta = gtk.CellRendererText()
    cboxa.pack_start(rendtexta, True)
    cboxa.add_attribute(rendtexta, "text", 0)
    cboxa.set_entry_text_column(0)
    cboxa.set_active(0)
    cboxa.connect("changed", self.on_region_changed)
    hbxa.add(cboxa)
    
    #button area
    butcanc = gtk.Button("Cancel")
    self.action_area.add(butcanc)
    butcanc.connect("clicked", gtk.main_quit)
    
    butgenpr = gtk.Button("Generate land details")
    self.action_area.add(butgenpr)
    butgenpr.connect("clicked", self.on_butgendet_clicked)

    self.show_all()
    return mwin
    
  #callback method, setting base region parameter 
  def on_region_changed(self, widget):
    refmode = widget.get_model()
    self.region = refmode.get_value(widget.get_active_iter(), 1)
    
  #callback method, generate land details
  def on_butgendet_clicked(self, widget):
    #base color for grass
    self.addmaskp(self.bgl)
    self.bgl.name = self.region    
    if (self.bgl.name == "grass"):
      self.cgradmap(self.bgl, self.colorgrassdeep, self.colorgrasslight)
    elif (self.bgl.name == "sand"):
      self.cgradmap(self.bgl, self.colordesertdeep, self.colordesertlight)
    elif (self.bgl.name == "ice"):
      self.cgradmap(self.bgl, self.colorarcticdeep, self.colorarcticlight)
      
    self.noisel = self.makenoisel(self.bgl.name + "texture", 3, OVERLAY_MODE)
    self.addmaskp(self.noisel)
    
    #create an embossing effect using a bump map
    self.bumpmapl = self.makenoisel(self.bgl.name + "bumpmap", 15, NORMAL_MODE, True)
    pdb.gimp_item_set_visible(self.bumpmapl, False)
    self.basebumpsl = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, self.bgl.name + "bumps", 100, OVERLAY_MODE)
    self.img.add_layer(self.basebumpsl, 0)
    colfillayer(self.img, self.basebumpsl, (128, 128, 128)) #make layer 50% gray

    pdb.plug_in_bump_map_tiled(self.img, self.basebumpsl, self.bumpmapl, 120, 45, 3, 0, 0, 0, 0, True, False, 2) #2 = sinusoidal
    self.addmaskp(self.basebumpsl)
    
    self.on_job_done()


#class to generate the dirt on the terrain
class DirtDetails(TLSbase):
  #constructor
  def __init__(self, image, tdraw, layermask, channelmask, *args):
    mwin = TLSbase.__init__(self, image, tdraw, None, layermask, channelmask, *args)
    self.bumpmapl = None
    self.basebumpsl = None
    self.smp = 50
    
    #colors
    self.colordirt = (128, 107, 80) #med dirt, a moderate brown

    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Adding dirt to the map?")
    hbxa.add(laba)
    
    #button area
    butcanc = gtk.Button("No")
    self.action_area.add(butcanc)
    butcanc.connect("clicked", self.on_butcanc_clicked)
    
    butgendrt = gtk.Button("Yes")
    self.action_area.add(butgendrt)
    butgendrt.connect("clicked", self.on_butgendrt_clicked)

    self.show_all()
    return mwin

  #method to make the more complex noise for dirt: should be combined with the land profile to have dirt close to the coast if a coast is present
  def makedirtnoisel(self, lname, pixsize):
    #preparing the noiselayer generation
    if self.maskl is not None:
      masklcopy = self.maskl.copy()
      self.img.add_layer(masklcopy, 0)
      pdb.plug_in_gauss(self.img, masklcopy, self.smp, self.smp, 0)
    
      #adding the noise layer mixed with the copy mask
      self.noisel = self.makenoisel(lname, pixsize, DIFFERENCE_MODE)
      self.noisel = pdb.gimp_image_merge_down(self.img, self.noisel, 0)
      pdb.gimp_invert(self.noisel)
      
    else:
      #just generating a normal noise layer
      self.noisel = self.makenoisel(lname, pixsize, NORMAL_MODE)
      
    self.noisel.name = "dirtnoisemask"


    #correcting the mask color levels
    commtxt = "Set minimum, maximum and gamma to edit the B/W ratio in the image.\n"
    commtxt += "The white regions will be covered by dirt."
    cld = CLevDialog(self.img, self.noisel, commtxt, CLevDialog.LEVELS, [CLevDialog.INPUT_MIN, CLevDialog.GAMMA, CLevDialog.INPUT_MAX], "Set input levels", self, gtk.DIALOG_MODAL)
    cld.run()
    resl = cld.reslayer
    cld.destroy()
    return resl

  #callback method, skipping the dirt adding
  def on_butcanc_clicked(self, widget):
    self.on_job_done()

  #callback method, generate the layers to create the dirt
  def on_butgendrt_clicked(self, widget):
    self.makebgl(self.colordirt)
    self.bgl.name = "dirt"
    
    #adding some effect to the layer to make it like dirt
    pdb.plug_in_hsv_noise(self.img, self.bgl, 4, 11, 10, 22)
    pdb.plug_in_bump_map_tiled(self.img, self.bgl, self.bgl, 120, 45, 3, 0, 0, 0, 0, True, False, 2) #2 = sinusoidal
    
    oknoise = True
    while oknoise:
      self.noisel = self.makedirtnoisel("dirtnoise", 16)
      
      #dialog checking that the user is satisfied with the result
      infodi = gtk.Dialog(title="Checking dialod", parent=self)
      ilabel = gtk.Label("Press OK if you are satisfied with the current mask.\nPress Cancel to generate a new mask for the dirt.")
      infodi.vbox.add(ilabel)
      ilabel.show()
      infodi.add_button("Cancel", gtk.RESPONSE_CANCEL)
      infodi.add_button("OK", gtk.RESPONSE_OK)
      useransw = infodi.run()
      
      if (useransw == gtk.RESPONSE_OK):
        oknoise = False
      elif (useransw == gtk.RESPONSE_CANCEL):
        pdb.gimp_image_remove_layer(self.img, self.noisel)

      infodi.destroy()
    
    #applying some masks
    self.addmaskp(self.bgl, False, True)
    maskbis = self.addmaskp(self.bgl, False, False) #readding but not applying, we need to work on the second mask

    noisemask = self.addmaskp(self.noisel)
    pdb.plug_in_gauss(self.img, self.noisel, 10, 10, 0)
    pdb.plug_in_spread(self.img, self.noisel, 10, 10)    
    self.addmaskp(self.noisel) #here called again to apply the mask
    
    #applying the mask, final step
    if self.maskl is not None:
      masklcopy = self.maskl.copy()
      self.img.add_layer(masklcopy, 1)      
      self.noisel = pdb.gimp_image_merge_down(self.img, self.noisel, 0)

    pdb.gimp_edit_copy(self.noisel)
    flsel = pdb.gimp_edit_paste(maskbis, False)
    pdb.gimp_floating_sel_anchor(flsel)

    pdb.gimp_item_set_visible(self.noisel, False)
    pdb.gimp_layer_set_opacity(self.bgl, 55)
    
    self.on_job_done()


#class for building stuffs in ristrected selected areas. Intented to be used as an abstract class and providing common methods.
class BuildAddition(TLSbase):
  #constructor
  def __init__(self, image, tdraw, layermask, channelmask, *args):
    mwin = TLSbase.__init__(self, image, tdraw, None, layermask, channelmask, *args)
    self.addingchannel = None
    
    #No Gui here, it is buildt in the child classes as it may change from class to class.
    
    self.show_all()
    return mwin
  
  #method, draw stuffs. Is etmpy, will be overridden by child classes
  def drawadding(self):
    pass
  
  #method to generate random selection (mask profile)
  def random_selecting(self, textes):
    baselayer = pdb.gimp_layer_new(self.img, self.img.width, self.img.height, 0, textes["baseln"] + "base", 100, 0) #0 = normal mode
    self.img.add_layer(baselayer, 0)
    colfillayer(self.img, baselayer, (255, 255, 255))
    mounts = MaskProfile(textes, self.img, baselayer, self.maskl, "Building " + textes["baseln"] + " mass", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    mounts.run()
    self.addingchannel = mounts.channelms
    
    #hiding not needed stuffs
    pdb.gimp_item_set_visible(mounts.bgl, False)
    pdb.gimp_item_set_visible(mounts.noisel, False)
    pdb.gimp_item_set_visible(mounts.clipl, False)
    pdb.gimp_item_set_visible(mounts.maskl, False)
    
    mounts.destroy()
    self.drawadding()
    
  #method to let the user to select the area by hand and generate the mask profile.
  def hand_selecting(self, textes):
    #dialog telling to select the area where to place the mountains
    infodi = gtk.Dialog(title="Info", parent=self)
    imess = "Select the area where you want to place the "+ textes["baseln"] + " with the lazo tool or another selection tool.\n"
    imess += "When you have a selection, press Ok. Press Cancel to clear the current selection and start it again."
    ilabel = gtk.Label(imess)
    infodi.vbox.add(ilabel)
    ilabel.show()
    infodi.add_button("Cancel", gtk.RESPONSE_CANCEL)
    infodi.add_button("Ok", gtk.RESPONSE_OK)
    diresp = infodi.run()

    if (diresp == gtk.RESPONSE_OK):
      if not pdb.gimp_selection_is_empty(self.img):
        self.addingchannel = pdb.gimp_selection_save(self.img)
        pdb.gimp_selection_none(self.img)
        infodi.destroy()
        self.drawadding()
      else:
        infodib = gtk.Dialog(title="Warning", parent=infodi)
        ilabelb = gtk.Label("You have to create a selection!")
        infodib.vbox.add(ilabelb)
        ilabelb.show()
        infodib.add_button("Ok", gtk.RESPONSE_OK)
        rr = infodib.run()

        if rr == gtk.RESPONSE_OK:
          infodib.destroy()
          infodi.destroy()
          self.hand_selecting(self, textes)

    elif (diresp == gtk.RESPONSE_CANCEL):
      pdb.gimp_selection_none(self.img)
      infodi.destroy()
      self.hand_selecting(self, textes)


#class to generate the mountains
class MountainsBuild(BuildAddition):
  #constructor
  def __init__(self, image, tdraw, layermask, channelmask, *args):
    mwin = BuildAddition.__init__(self, image, tdraw, layermask, channelmask, *args)
    self.mountainsangular = None
    self.cpvlayer = None
    self.embosslayer = None
    self.addsnow = True
    
    smoothbase = [0, 0.03, 0.1, 0.2]
    self.smoothlist = ["None", "Short", "Medium", "Long"]
    self.smoothvallist = [0.5 * i * (self.img.width + self.img.height) for i in smoothbase]
    self.smoothval = 0 #will be reinitialized during construction
    
    self.mtextes = {"baseln" : "mountains", \
    "namelist" : ["no mountains", "sparse", "mountain chain", "central mountain mass", "central valley", "customized"], \
    "toplab" : "In the final result: white represent where mountains are drawn."}
    
    #Designing the interface
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Adding mountains to the map.")
    hbxa.add(laba)
    
    #new row
    hbxc = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxc)
    
    labc = gtk.Label("Select smoothing range for mountains feet")
    hbxc.add(labc)
    
    boxmodelc = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT)
    
    #filling the model for the combobox
    for i, j in zip(self.smoothlist, self.smoothvallist):
      irow = boxmodelc.append(None, [i, j])

    self.smoothval = self.smoothvallist[2]

    cboxc = gtk.ComboBox(boxmodelc)
    rendtextc = gtk.CellRendererText()
    cboxc.pack_start(rendtextc, True)
    cboxc.add_attribute(rendtextc, "text", 0)
    cboxc.set_entry_text_column(0)
    cboxc.set_active(2)
    cboxc.connect("changed", self.on_smooth_changed)
    hbxc.add(cboxc)
    
    #new row
    hbxb = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxb)
    chbb = gtk.CheckButton("Add snow on mountain's top.")
    chbb.set_active(self.addsnow)
    chbb.connect("toggled", self.on_chbb_toggled)
    hbxb.add(chbb)
        
    #button area
    butcanc = gtk.Button("Cancel")
    self.action_area.add(butcanc)
    butcanc.connect("clicked", self.on_butcanc_clicked)
    
    butgenrnd = gtk.Button("Random")
    self.action_area.add(butgenrnd)
    butgenrnd.connect("clicked", self.on_butgenrdn_clicked)

    self.butgenhnp = gtk.Button("Hand-placed")
    self.action_area.add(self.butgenhnp)
    self.butgenhnp.connect("clicked", self.on_butgenhnp_clicked)
    
    self.show_all()
    return mwin
  
  #callback method
  def on_butcanc_clicked(self, widget):
    self.on_job_done()

  #callback method, set the adding snow variable
  def on_chbb_toggled(self, widget):
    self.addsnow = widget.get_active()

  #callback method, randomly generate a selection where mountains are drawn
  def on_butgenrdn_clicked(self, widget):
    self.random_selecting(self.mtextes)
    
  #callback method, allow the user to draw a selection where mountains are drawn
  def on_butgenhnp_clicked(self, widget):
    self.hand_selecting(self.mtextes)
  
  #method, set the smooth parameter
  def on_smooth_changed(self, widget):
    refmode = widget.get_model()
    self.smoothval = refmode.get_value(widget.get_active_iter(), 1)
    
  #override method, drawing the mountains in the selection (when the method is called, a selection channel for the mountains should be already present)
  def drawadding(self):
    self.addingchannel.name = self.mtextes["baseln"] + "mask"
    
    #creating blurred base
    self.bgl = self.makeunilayer(self.mtextes["baseln"] + "blur", (0, 0, 0))
    pdb.gimp_image_select_item(self.img, 2, self.addingchannel)
    colfillayer(self.img, self.bgl, (255, 255, 255))
    pdb.gimp_selection_none(self.img)
    if self.smoothval > 0:
      pdb.plug_in_gauss(self.img, self.bgl, self.smoothval, self.smoothval, 0)

    #creating noise
    self.noisel = self.makeunilayer(self.mtextes["baseln"] + "noise", (0, 0, 0))
    pdb.gimp_image_select_item(self.img, 2, self.addingchannel)
    if self.smoothval > 0:
      pdb.gimp_selection_feather(self.img, self.smoothval/2)
    paramstr = str(random.random() * 9999999999)
    paramstr += " 10.0 10.0 8.0 2.0 0.30 1.0 0.0 planar lattice_noise NO ramp fbm smear 0.0 0.0 0.0 fg_bg"
    try:
      pdb.plug_in_fimg_noise(self.img, self.noisel, paramstr) #using felimage plugin
    except:
      pdb.plug_in_solid_noise(self.img, self.noisel, False, False, random.random() * 9999999999, 16, 4, 4)
    
    #creating angular gradient
    self.mountainsangular = self.makeunilayer(self.mtextes["baseln"] + "angular", (0, 0, 0))
    #drawing the gradients: #0 (first) = normal mode, 0 (second) linear gradient, 6 (third): shape angular gradient, True (eighth): supersampling
    pdb.gimp_edit_blend(self.mountainsangular, 0, 0, 6, 100, 0, 0, True, True, 4, 3.0, True, 0, 0, self.img.width, self.img.height)
    pdb.gimp_selection_none(self.img)
    
    #editing level modes and color levels
    pdb.gimp_layer_set_mode(self.noisel, ADDITION_MODE)
    pdb.gimp_layer_set_mode(self.mountainsangular, ADDITION_MODE)
    pdb.gimp_levels(self.bgl, 0, 0, 255, 1.0, 0, 85) #regulating color levels, channel = #0 (second parameter) is for histogram value
    inhh = self.get_brightness_max(self.noisel)
    pdb.gimp_levels(self.noisel, 0, 0, inhh, 1.0, 0, 50) #regulating color levels, channel = #0 (second parameter) is for histogram value
    
    #editing color curves
    ditext = "Try to eliminate most of the brightness by lowering the top-right control point\nand adding other points at the level of the histogram counts."
    cdd = CCurveDialog(self.img, self.mountainsangular, ditext, "Setting color curve", self, gtk.DIALOG_MODAL)
    cdd.run()
    self.mountainsangular = cdd.reslayer
    
    self.cpvlayer = pdb.gimp_layer_new_from_visible(self.img, self.img, "visible")
    self.img.add_layer(self.cpvlayer, 0)
    cdd.destroy()
    
    #editing color curves, again
    ditextb = "Try to add one or more control points below the diagonal\nin order to better define mountains peaks."
    cddb = CCurveDialog(self.img, self.cpvlayer, ditextb, "Setting color curve", self, gtk.DIALOG_MODAL)
    cddb.run()
    self.cpvlayer = cddb.reslayer
    
    #adding emboss effect
    self.embosslayer = cddb.reslayer.copy()
    self.embosslayer.name = self.mtextes["baseln"] + "emboss"
    self.img.add_layer(self.embosslayer, 0)
    cddb.destroy()
    pdb.plug_in_emboss(self.img, self.embosslayer, 30.0, 30.0, 20.0, 1)
    
    #fixing outside selection
    pdb.gimp_image_select_item(self.img, 2, self.addingchannel)
    if self.smoothval > 0:
      pdb.gimp_selection_feather(self.img, self.smoothval/2)
    pdb.gimp_selection_invert(self.img) #inverting selection
    colfillayer(self.img, self.embosslayer, (128, 128, 128))
    
    #hiding not needed layers
    pdb.gimp_item_set_visible(self.bgl, False)
    pdb.gimp_item_set_visible(self.noisel, False)
    pdb.gimp_item_set_visible(self.mountainsangular, False)
    pdb.gimp_item_set_visible(self.cpvlayer, False)
    pdb.gimp_layer_set_mode(self.embosslayer, OVERLAY_MODE)
    pdb.gimp_selection_none(self.img)

    #adding snow
    if self.addsnow:
      pdb.gimp_item_set_visible(self.cpvlayer, True)
      pdb.gimp_layer_set_mode(self.cpvlayer, SCREEN_MODE)
      commtxt = "Set minimum threshold to regulate the amount of the snow."
      cldc = CLevDialog(self.img, self.cpvlayer, commtxt, CLevDialog.THRESHOLD, [CLevDialog.THR_MIN], "Set lower threshold", self, gtk.DIALOG_MODAL)
      cldc.run()
      self.cpvlayer = cldc.reslayer
      pdb.plug_in_gauss(self.img, self.cpvlayer, 5, 5, 0)
      pdb.gimp_layer_set_opacity(self.cpvlayer, 65)
      cldc.destroy()
    
    self.on_job_done()


#class for the customized GUI
class MainApp(gtk.Window):
  #constructor
  def __init__(self, image, drawab, *args):
    mwin = gtk.Window.__init__(self, *args)
    self.set_border_width(10)
    
    #internal arguments
    self.img = image
    self.drawab = drawab
    
    #Obey the window manager quit signal:
    self.connect("destroy", gtk.main_quit)
    
    #Designing the interface
    vbx = gtk.VBox(spacing=10, homogeneous=True)
    self.add(vbx)
    
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    vbx.add(hbxa)
    
    butgenmap = gtk.Button("Generate map randomly")
    hbxa.add(butgenmap)
    butgenmap.connect("clicked", self.on_butgenmap_clicked)

    butusemap = gtk.Button("Use current image as base map")
    hbxa.add(butusemap)
    butusemap.connect("clicked", self.on_butusemap_clicked)

    self.show_all()
    return mwin
    
  #callback method to generate the map randomly
  def on_butgenmap_clicked(self, widget):
    pdb.gimp_context_set_foreground((0, 0, 0)) #set foreground color to black
    pdb.gimp_context_set_background((255, 255, 255)) #set background to white

    landtextes = {"baseln" : "land", \
    "namelist" : ["no water", "archipelago/lakes", "simple coastline", "island", "big lake", "customized"], \
    "toplab" : "In the final result: white represent land and black represent water."}
    
    land = MaskProfile(landtextes, self.img, self.drawab, None, "Building land mass", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    land.run()
    layermask = land.maskl
    channelmask = land.channelms
    
    landbg = self.drawab
    if (land.chtype > 0):
      #create a copy of the landmass to use as base layer for the watermass
      waterbg = land.maskl.copy()
      waterbg.name = "seashape"
      self.img.add_layer(waterbg, 0)
            
      water = WaterProfile(self.img, waterbg, layermask, channelmask, "Building water mass", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
      water.run()

      #create a copy of the landmass to use as base layer for the landmass decoration      
      landbg = water.bgl.copy()
      self.img.add_layer(landbg, 0)

    landbg.name = "base"
    landdet = BaseDetails(self.img, landbg, layermask, channelmask, "Building land details", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    landdet.run()
    
    dirtd = DirtDetails(self.img, None, layermask, channelmask, "Building dirt", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    dirtd.run()
    
    mount = MountainsBuild(self.img, None, layermask, channelmask, "Building mountains", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    mount.run()
    
  #callback method to use current image as map
  def on_butusemap_clicked(self, widget):
    pass


#The function to be registered in GIMP
def python_make_landmap(img, tdraw):
  #query the procedure database
  nummfelimg, procedure_names = pdb.gimp_procedural_db_query("plug-in-fimg-noise", ".*", ".*", ".*", ".*", ".*", ".*")
  if nummfelimg == 0:
    pdb.gimp_message("Warning: you need to install the felimage plugin to use all the features of this plugin properly.\nWithout the felimage plugin, the mountains will be of poor quality.")  
    
  mapp = MainApp(img, tdraw)
  gtk.main()


#The command to register the function
register(
  "python-fu_make_landmap",
  "python-fu_make_landmap",
  "Generate or edit a regional map. Start from an image with a single layer with white background: pop up dialogs appear to guide the user in the process.",
  "Valentino Esposito",
  "Valentino Esposito",
  "2018",
  "<Image>/Tools/LandMap",
  "RGB*, GRAY*, INDEXED*",
  [],
  [],
  python_make_landmap
  )

#The main function to activate the script
main()
