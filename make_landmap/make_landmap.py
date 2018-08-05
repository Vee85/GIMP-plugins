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

#This script draws a regional map. Can be used to generate gdr-like maps. It mostly follows the guidelines of a tutorial on http://www.cartographersguild.com/
#This script must be placed in ~/.gimp-n.m/plug-ins
#where n.m is the gimp version (e.g. 2.8)

#@@@ do so that light comes from the same direction (such as azimuth and angle of various plugins)
#@@@ add gulf / peninsula type for land using conical shaped gradient (and similar for mountains and forests)
#@@@ adjust general scale to image size (es when generating the solid noise)
#@@@ mountains improvements: add more control on smooth: possibility to better regulate smooth parameter. How?
#@@@ forests improvements: different color set to make different kind of forests?
#@@@ make rotation instead of directions in maskprofile
#@@@ separate AdditionalDetBuild in a separate step making full use of LocalBuilder

import sys
import os
import math
import random
import gtk
import gobject
from gimpfu import *


#generic function used to convert a 65535 RGB color gobject in a 255 tuple RGB color
def gdkcoltorgb(gdkc):
  red = int(gdkc.red_float * 255)
  green = int(gdkc.green_float * 255)
  blue = int(gdkc.blue_float * 255)
  return (red, green, blue)

#generic function used to convert a 255 tuple RGB color in a 65535 RGB color gobject
def rgbcoltogdk(rr, gg, bb):
  red = int(rr * (65535 / 255))
  green = int(gg * (65535 / 255))
  blue = int(bb * (65535 / 255))
  return gtk.gdk.Color(red, green, blue)

#generic function to fill a layer with a color
def colfillayer(image, layer, rgbcolor):
  oldfgcol = pdb.gimp_context_get_foreground()
  pdb.gimp_context_set_foreground(rgbcolor) #set foreground color
  pdb.gimp_edit_bucket_fill(layer, 0, 0, 100, 255, True, pdb.gimp_image_width(image)/2, pdb.gimp_image_height(image)/2) #0 (first): filling the layer with foreground color
  pdb.gimp_context_set_foreground(oldfgcol)


#dictonary storing the color definitions, to be used by other classes
colordict = dict()
colordict["grass"] = {"deep" : (76, 83, 41), "light" : (149, 149, 89)} #a dark green color, known as ditch and a light green color, known as high grass
colordict["ground"] = {"deep" : (75, 62, 44), "light" : (167, 143, 107)} #a dark brown color, lowest dirt and a light brown color, high dirt
colordict["sand"] = {"deep" : (150, 113, 23), "light" : (244, 164, 96)} #a relatively dark brown, known as sand dune and a light brown almost yellow, known as sandy brown
colordict["ice"] = {"deep" : (128, 236, 217), "light" : (232, 232, 232)} #a clear blue and a dirty white


#class to let the user setting the colors edge of a color map
class ColorMapper(gtk.Dialog):
  #constructor
  def __init__(self, labtxt, bicolor=False, *args):
    mwin = gtk.Dialog.__init__(self, *args)
    self.set_border_width(10)

    if bicolor:
      self.wcol = ["light", "deep"]
    else:
      self.wcol = ["the"]
      
    self.butcolors = {}
    self.chcol = {}

    #Designing the interface
    #new row
    laba = gtk.Label(labtxt)
    self.vbox.add(laba)

    #new row
    hbxb = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxb)

    for l in self.wcol:
      tt = "Select " + l + " color"
      labb = gtk.Label(tt)
      hbxb.add(labb)
      hbxb.add(self.addbutcol(l, tt, (0, 0, 0)))

    #button area
    self.add_button("Cancel", gtk.RESPONSE_CANCEL)
    self.add_button("Ok", gtk.RESPONSE_OK)

    self.show_all()
    return mwin

  #callback method
  def on_butcolor_clicked(self, widget, key):
    self.chcol[key] = gdkcoltorgb(widget.get_color())

  #make color button chooser
  def addbutcol(self, key, dtitle, rgbcol):
    self.butcolors[key] = gtk.ColorButton()
    self.butcolors[key].set_title(dtitle)
    self.chcol[key] = rgbcol
    self.butcolors[key].connect("color-set", self.on_butcolor_clicked, key)
    return self.butcolors[key]
    

#class to adjust the color levels/threshold of a layer, reproducing a simpler interface to the GIMP color levels dialog or the GIMP color threshold dialog. 
class CLevDialog(gtk.Dialog):
  #class constants (used as a sort of enumeration)
  LEVELS = 0
  THRESHOLD = 1
  OPACITY = 2
  
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
  def __init__(self, image, layer, ltext, ctype, modes, grouplayer, *args):
    dwin = gtk.Dialog.__init__(self, *args)
    self.set_border_width(10)
    self.connect("destroy", gtk.main_quit)

    #internal arguments
    self.ctype = ctype
    self.modes = modes
    self.groupref = grouplayer
    self.img = image
    self.origlayer = layer
    self.reslayer = None
    if self.groupref is None:
      llst = self.img.layers
    else:
      llst = self.groupref.layers
    self.lapos = [j for i, j in zip(llst, range(len(llst))) if i.name == self.origlayer.name][0]

    self.inlow = 0 #threshold color set to minimum (if used in the three channel (RGB) is black)
    self.inhigh = 255 #threshold color set to maximum (if used in the three channel (RGB) is white)
    self.gamma = 1.0 #gamma value for input color
    self.outlow = 0 #threshold color set to minimum (if used in the three channel (RGB) is black)
    self.outhigh = 255 #threshold color set to maximum (if used in the three channel (RGB) is white)
    self.thrmin = 127 #threshold color set to middle 
    self.thrmax = 255 #threshold color set to max
    self.opa = 50
    
    if self.ctype not in [CLevDialog.LEVELS, CLevDialog.THRESHOLD, CLevDialog.OPACITY]:
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
    elif self.ctype == CLevDialog.OPACITY:
      self.modes = [0]
    
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
    elif self.ctype == CLevDialog.OPACITY:
      adjlist.append(gtk.Adjustment(self.opa, 0, 100, 1, 10))
      labtxt.append("Opacity")
          
    #making the scale and spinbuttons for the adjustments
    for adj, ww, lt in zip(adjlist, self.modes, labtxt):
      #new row
      hboxes.append(gtk.HBox(spacing=10, homogeneous=False))
      self.vbox.add(hboxes[-1])
    
      labb.append(gtk.Label(lt))
      hboxes[-1].add(labb[-1])
      
      scab.append(gtk.HScale(adj))
      scab[-1].set_size_request(120, 45)
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
    pdb.gimp_image_insert_layer(self.img, self.reslayer, self.groupref, self.lapos)
    pdb.gimp_item_set_visible(self.origlayer, False)
  
  #callback method, apply the new value
  def on_value_changed(self, widget, m):
    if self.ctype == CLevDialog.LEVELS:
      self.make_reslayer()
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
      self.make_reslayer()
      if (m == CLevDialog.THR_MIN):
        self.thrmin = widget.get_value()
      if (m == CLevDialog.THR_MAX):
        self.thrmax = widget.get_value()
      
      pdb.gimp_threshold(self.reslayer, self.thrmin, self.thrmax) #regulating threshold levels
    
    elif self.ctype == CLevDialog.OPACITY:
      self.opa = widget.get_value()
      pdb.gimp_layer_set_opacity(self.origlayer, self.opa)
    
    pdb.gimp_displays_flush()

  #callback method for ok button
  def on_butok_clicked(self, widget):
    if self.ctype in [CLevDialog.LEVELS, CLevDialog.THRESHOLD]:
      rname = self.origlayer.name
      pdb.gimp_image_remove_layer(self.img, self.origlayer)
      self.reslayer.name = rname
    elif self.ctype == CLevDialog.OPACITY:
      pass
      
    self.hide()


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

    return dwin

  #nested class representing a graphic marker in the drawing area
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

        mm = self.CCMarker(ev.x, ev.y, att)
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
  def __init__(self, image, layer, grouplayer, ltext, *args):
    dwin = BDrawDial.__init__(self, ltext, *args)

    #internal arguments
    self.img = image
    self.groupref = grouplayer
    self.origlayer = layer
    self.reslayer = None
    self.cns = None
    if self.groupref is None:
      llst = self.img.layers
    else:
      llst = self.groupref.layers
    self.lapos = [j for i, j in zip(llst, range(len(llst))) if i.name == self.origlayer.name][0]
    
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
    return mx, my

  #method, create the result layer
  def make_reslayer(self):
    #deleting the reslayer and recreating if it already exists
    if self.reslayer is not None:
      pdb.gimp_image_remove_layer(self.img, self.reslayer)
    
    pdb.gimp_item_set_visible(self.origlayer, True)
    self.reslayer = self.origlayer.copy()
    pdb.gimp_image_insert_layer(self.img, self.reslayer, self.groupref, self.lapos)
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
    self.markers = [self.CCMarker(self.xfr, self.drh - self.yfr, True), self.CCMarker(self.drw - self.xfr, self.yfr, True)]
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
  #class constants
  PREVIOUS = 0
  NEXT = 1
  
  #constructor
  def __init__(self, image, basemask, layermask, channelmask, mandst, *args):
    mwin = gtk.Dialog.__init__(self, *args)
    self.set_border_width(10)
    
    #Obey the window manager quit signal:
    self.connect("destroy", gtk.main_quit)
    
    #internal argument for navigation (these point to other TLSbase child)
    self.mandatorystep = mandst #this should be set during object instance creation
    self.prevd = None
    self.nextd = None
    self.chosen = None
    
    #internal arguments
    self.img = image
    self.refwidth = image.width
    self.refheight = image.height
    self.groupl = []
    self.bgl = None
    self.noisel = None
    self.clipl = None
    self.baseml = basemask
    self.maskl = layermask
    self.channelms = channelmask
    self.namelist = None
    self.thrc = 0 #will be selected later
    self.smoothprofile = 0
    self.generated = False
    
    #nothing in the dialog: labels and buttons are created in the child classes
    
    return mwin
    
  #method to set the references to other TLSbase child instances
  def setreferences(self, p, n):
    self.prevd = p
    self.nextd = n
    
    #safety tests to avoid errors in case self.butprev/self.butnext have not been created by calling the add_button_nextprev method
    try:
      if self.prevd is None:
        self.butprev.set_sensitive(False)
    except AttributeError:
      pass
    
    try:
      if self.mandatorystep or self.nextd is None:
        self.butnext.set_sensitive(False)
    except AttributeError:
      pass
  
  #method, setting internal variable 'generated'
  def setgenerated(self, b):
    self.generated = b
    if self.mandatorystep:
      try:
        self.butnext.set_sensitive(self.generated)
      except AttributeError:
        pass
        
  #method to close the dialog at the end
  def on_job_done(self):
    pdb.gimp_displays_flush()
    self.hide()
    
  #callback method to quit from the dialog looping
  def on_quit(self, widget):
    self.chosen = None
    self.afterclosing(0)
    if not self.generated:
      self.cleandrawables()
    self.on_job_done()
    
  #method, generate the stuffs. To be overrided by child classes
  def generatestep(self):
    raise NotImplementedError("child class must implement on_butgen_clicked method")
  
  #callback method, set the next or previous instance which will be called by another method
  def on_setting_np(self, widget, pp):
    close = True
    if pp == TLSbase.PREVIOUS:
      self.cleandrawables()
      self.setgenerated(False)
      self.chosen = self.prevd
    elif pp == TLSbase.NEXT:
      if self.mandatorystep and not self.generated:
        close = False
        self.chosen = None
      else:
        self.chosen = self.nextd
      self.afterclosing(1)

    if close:
      self.on_job_done()
  
  #empty method to clean layer during regeneration. It will be overrided by child classes
  def cleandrawables(self):
    raise NotImplementedError("Child class must implement cleandrawables method")

  #method to get the last grouplayer (the one in use) or None
  def getgroupl(self):
    if isinstance(self.groupl, list):
      if len(self.groupl) > 0:
        return self.groupl[-1]
      else:
        return None
    elif isinstance(self.groupl, gimp.GroupLayer):
      return self.groupl
    elif self.groupl is None:
      return None

  #method, loading the group layer if needed
  def loadgrouplayer(self, namegroup):
    for lg in self.img.layers:
      if namegroup in lg.name and isinstance(lg, gimp.GroupLayer):
        self.groupl.append(lg)

  #empty method, childs must implement it in order to recognize layers, channels and vectors belonging to them. It will be overrided by child classes
  def loaddrawables(self):
    raise NotImplementedError("Child class must implement loaddrawables method")

  #method to be called by loaddrawables child's methods, checking if there were layers to be loaded (actually it checks self.bgl or self.groupl)
  def loaded(self):
    res = False
    if isinstance(self.groupl, list):
      if len(self.groupl) > 0:
        res = True
      elif self.bgl is not None:
        res = True
    elif isinstance(self.groupl, gimp.GroupLayer):
      res = True

    if res:
      self.setgenerated(True)
    return res
    
  #method, adding the cancel button to the button area 
  def add_button_quit(self):
    self.butquit = gtk.Button("Quit")
    self.action_area.add(self.butquit)
    self.butquit.connect("clicked", self.on_quit)
     
  #method, adding the previous and next button to the button area
  def add_button_nextprev(self): 
    self.butprev = gtk.Button("Previous")
    self.action_area.add(self.butprev)
    self.butprev.connect("clicked", self.on_setting_np, TLSbase.PREVIOUS)

    self.butnext = gtk.Button("Next")
    self.action_area.add(self.butnext)
    self.butnext.connect("clicked", self.on_setting_np, TLSbase.NEXT)

  #method to set a group layer for the object
  def makegrouplayer(self, gname, pos):
    if isinstance(self.groupl, list):
      self.groupl.append(pdb.gimp_layer_group_new(self.img))
      self.groupl[-1].name = gname
      pdb.gimp_image_insert_layer(self.img, self.groupl[-1], None, pos)
    else:
      raise RuntimeError("An error as occurred when making a new GroupLayer. The makegrouplayer must have been called when self.groupl is not a list.")
  
  #method to copy the background layer from an already existing layer
  def copybgl(self, blayer, blname):
    self.bgl = blayer.copy()
    self.bgl.name = blname
    pdb.gimp_image_insert_layer(self.img, self.bgl, self.getgroupl(), 0)
    
  #method to set some stuffs before a run() call. To be overrided by the child classes if needed, but not mandatory
  def setbeforerun(self):
    pass

  #method to perform any action at the pressing of the next or quit button (even if the step has not been generated). To be overrided by the child classes if needed, but not mandatory
  def afterclosing(self, who):
    pass
  
  #method to delete drawable (layers and channel masks) associated to the TLSbase child instance. Drawable of TLSbase are deleted, drawable of childs must be given as arguments
  def deletedrawables(self, *drawables):
    basetuple = (self.bgl, self.noisel, self.clipl) #not deleting self.baselm, self.maskl, self.channelms and self.groupl as they are shared by various instances
    deltuple = basetuple + drawables

    #deleting the list
    pdb.gimp_plugin_set_pdb_error_handler(1)
    for dr in deltuple:
      try:
        if isinstance(dr, (gimp.Layer, gimp.GroupLayer)):
          pdb.gimp_image_remove_layer(self.img, dr)
        elif isinstance(dr, gimp.Channel):
          pdb.gimp_image_remove_channel(self.img, dr)
        elif isinstance(dr, gimp.Vectors):
          pdb.gimp_image_remove_vectors(self.img, dr)
      except RuntimeError, e:   #catching and neglecting runtime errors due to not valid ID, likely due to merged layers which do not exist anymore
        pass
    
    pdb.gimp_plugin_set_pdb_error_handler(0)

  #method to get the maximum brightness from the pixel histogram of a layer
  def get_brightness_max(self, layer, channel=HISTOGRAM_VALUE):
    endr = 255
    found = False
    _, _, _, _, chk, _ = pdb.gimp_histogram(layer, channel, 0, endr)
    if chk == 0:
      return -1
    while not found:
      _, _, _, pixels, count, _ = pdb.gimp_histogram(layer, channel, 0, endr)
      if count < pixels or endr == 0:
        found = True
      else:
        endr = endr - 1
        
    return endr
    
  #method to get the minimum brightness from the pixel histogram of a layer
  def get_brightness_min(self, layer, channel=HISTOGRAM_VALUE):
    startr = 0
    found = False
    _, _, _, _, chk, _ = pdb.gimp_histogram(layer, channel, startr, 255)
    if chk == 0:
      return -1
    while not found:
      _, _, _, pixels, count, _ = pdb.gimp_histogram(layer, channel, startr, 255)
      if count < pixels or startr == 255:
        found = True
      else:
        startr = startr + 1
        
    return startr

  #method to check if a pixel belongs to the area which would be selected using the given channel selection mask.
  def checkpixelcoord(self, x, y, chmask=None, threshold=0.5):
    if chmask is None:
      chmask = self.channelms

    if chmask is not None:
      color = pdb.gimp_image_pick_color(self.img, chmask, x, y, False, False, 0)
      if color.red > threshold and color.green > threshold and color.blue > threshold:
        return True

    return False
  
  #method, set the smoothprofile parameter
  def setsmoothprof(self, val):
    self.smoothprofile = val
  
  #method, copy the pixel map of a layer into a channel selection
  def layertochannel(self, llayer, pos, chname):
    reschannel = pdb.gimp_channel_new(self.img, self.img.width, self.img.height, chname, 100, (0, 0, 0))
    self.img.add_channel(reschannel, pos)
    
    pdb.gimp_selection_all(self.img)
    if not pdb.gimp_edit_copy(llayer):
      raise RuntimeError("An error as occurred while copying from the layer in TLSbase.layertochannel method!")
      
    flsel = pdb.gimp_edit_paste(reschannel, True)
    pdb.gimp_floating_sel_anchor(flsel)
    pdb.gimp_item_set_visible(reschannel, False)
    pdb.gimp_selection_none(self.img)
    return reschannel

  #method to use another function (such as makeunilayer, makenoisel, makeclipl) to generate a wider layer. In this case, full list of arguments except the final size must be provided as a tuple
  def makerotatedlayer(self, centered, angle, makingf, args):
    newsize = math.sqrt(math.pow(self.img.width, 2) + math.pow(self.img.height, 2))
    self.refwidth = newsize
    self.refheight = newsize
    resl = makingf(*args)
    self.refwidth = self.img.width
    self.refheight = self.img.height

    #aligning the centers (center of new layer equal to the center of the image
    if centered:
      xoff = self.img.width/2 - newsize/2
      yoff = self.img.height/2 - newsize/2
      pdb.gimp_layer_translate(resl, xoff, yoff)
    
    resl = pdb.gimp_item_transform_rotate(resl, angle, True, 0, 0) #0, 0, rotation center coordinates, negltected if autocenter is True
    pdb.gimp_layer_resize_to_image_size(resl)
    return resl
  
  #method to generate a uniformly colored layer (typically the background layer)
  def makeunilayer(self, lname, lcolor=None):
    res = pdb.gimp_layer_new(self.img, self.refwidth, self.refheight, 0, lname, 100, 0) #0 = normal mode
    pdb.gimp_image_insert_layer(self.img, res, self.getgroupl(), 0)
    if lcolor is None:      
      lcolor = (255, 255, 255) #make layer color white
    
    colfillayer(self.img, res, lcolor)
    pdb.gimp_displays_flush()
    return res
  
  #method to generate the noise layer
  def makenoisel(self, lname, xpix, ypix, mode=NORMAL_MODE, turbulent=False, normalise=False):
    noiselayer = pdb.gimp_layer_new(self.img, self.refwidth, self.refheight, 0, lname, 100, mode)
    pdb.gimp_image_insert_layer(self.img, noiselayer, self.getgroupl(), 0)
    pdb.plug_in_solid_noise(self.img, noiselayer, False, turbulent, random.random() * 9999999999, 15, xpix, ypix)
    if normalise:
      pdb.plug_in_normalize(self.img, noiselayer)
      pdb.plug_in_gauss(self.img, noiselayer, 5, 5, 0)
    
    return noiselayer
  
  #method to generate the clip layer
  def makeclipl(self, lname, commtxt): 
    cliplayer = pdb.gimp_layer_new(self.img, self.refwidth, self.refheight, 0, lname, 100, LIGHTEN_ONLY_MODE)
    pdb.gimp_image_insert_layer(self.img, cliplayer, self.getgroupl(), 0)
    colfillayer(self.img, cliplayer, (255, 255, 255)) #make layer color white
    
    cld = CLevDialog(self.img, cliplayer, commtxt, CLevDialog.LEVELS, [CLevDialog.OUTPUT_MAX], self.getgroupl(), "Set clip layer level", self, gtk.DIALOG_MODAL) #title = "sel clip...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    cld.run()
    cliplayer = cld.reslayer
    self.thrc = cld.outhigh
    cld.destroy()
    return cliplayer

  #method to merge two layer representing two masks
  def mergemasks(self):
    if self.baseml is not None and self.maskl is not None:
      if self.getgroupl() is None:
        llst = self.img.layers
      else:
        llst = self.getgroupl().layers
      mlpos = [j for i, j in zip(llst, range(len(llst))) if i.name == self.maskl.name][0]
      copybl = self.baseml.copy()
      pdb.gimp_image_insert_layer(self.img, copybl, self.getgroupl(), mlpos)
      pdb.gimp_layer_set_mode(copybl, DARKEN_ONLY_MODE)
      self.maskl = pdb.gimp_image_merge_down(self.img, copybl, 0)

  #method to make the final layer with the profile and save it in a channel.
  #remember: white = transparent, black = blocked
  def makeprofilel(self, lname):
    pdb.gimp_context_set_sample_merged(True)
    pdb.gimp_image_select_color(self.img, 2, self.clipl, (int(self.thrc), int(self.thrc), int(self.thrc))) #2 = selection replace
    pdb.gimp_context_set_sample_merged(False)
    pdb.gimp_selection_invert(self.img) #inverting selection
    self.maskl = self.makeunilayer(lname)
    
    if self.baseml is not None:
      #merging the mask with a previous mask
      pdb.gimp_selection_none(self.img)
      #smoothing new mask before merging
      if self.smoothprofile > 0:
        pdb.plug_in_gauss(self.img, self.maskl, self.smoothprofile, self.smoothprofile, 0)
      
      self.mergemasks()
      self.channelms = self.layertochannel(self.maskl, 0, "copiedfromlayer")
    else:
      self.channelms = pdb.gimp_selection_save(self.img)
      pdb.gimp_selection_none(self.img)
    
  #method to apply a channel mask to a layer 
  def addmaskp(self, layer, chmask=None, inverting=False, applying=False):
    if chmask is None:
      chmask = self.channelms
      
    if pdb.gimp_layer_get_mask(layer) is None:
      maskmode = 0 #white mask (full transparent)
      if (chmask is not None):
        maskmode = 6 #channel mask
        if (pdb.gimp_image_get_active_channel(self.img) is None): #checking if there is already an active channel
          pdb.gimp_image_set_active_channel(self.img, chmask) #setting the active channel: if there is no active channel, gimp_layer_create_mask will fail.
      
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

  #method to improve mask shape and making it more detailed
  def overdrawmask(self, basenoise, lname, smoothval=0, chmask=None, hideoriginal=False, hidefinal=False):
    if chmask is None:
      chmask = self.channelms

    #make a copy of the basenoise layer, so that the original layer is not overwritten
    copybn = basenoise.copy()
    copybn.name = lname + "copy"
    pdb.gimp_image_insert_layer(self.img, copybn, self.getgroupl(), 0)
    if hideoriginal:
      pdb.gimp_item_set_visible(basenoise, False)

    extralev = copybn.copy()
    extralev.name = lname + "level"
    pdb.gimp_image_insert_layer(self.img, extralev, self.getgroupl(), 0)
    pdb.gimp_levels(extralev, 0, 0, 255, 1, 80, 255) #regulating color levels, channel = #0 (second parameter) is for histogram value
    
    shapelayer = self.makeunilayer(lname + "shape", (0, 0, 0))
    pdb.gimp_image_select_item(self.img, 2, chmask)
    if smoothval > 0:
      pdb.gimp_selection_feather(self.img, smoothval)
    
    colfillayer(self.img, shapelayer, (255, 255, 255))
    pdb.gimp_selection_none(self.img)
    if smoothval > 0:
      pdb.plug_in_gauss(self.img, shapelayer, smoothval, smoothval, 0)
    
    pdb.gimp_layer_set_mode(shapelayer, MULTIPLY_MODE)
    shapelayer = pdb.gimp_image_merge_down(self.img, shapelayer, 0) #merging shapelayer with extralev
    commtxt = "Set the threshold until you get a shape you like"
    frshape = CLevDialog(self.img, shapelayer, commtxt, CLevDialog.THRESHOLD, [CLevDialog.THR_MIN], self.getgroupl(), "Set lower threshold", self, gtk.DIALOG_MODAL)
    frshape.run()
    
    shapelayer = frshape.reslayer
    pdb.gimp_image_select_color(self.img, 2, shapelayer, (255, 255, 255)) #2 = selection replace
    resmask = pdb.gimp_selection_save(self.img) #replacing forest mask with this one.
    resmask.name = lname + "defmask"
    pdb.gimp_selection_none(self.img)
    pdb.gimp_layer_set_mode(shapelayer, MULTIPLY_MODE)
    shapelayer = pdb.gimp_image_merge_down(self.img, shapelayer, 0)
    shapelayer.name = lname + "final"

    if hidefinal:
      pdb.gimp_item_set_visible(shapelayer, False)
    else:
      pdb.plug_in_colortoalpha(self.img, shapelayer, (0, 0, 0))

    return shapelayer, resmask


#class for building stuffs in the global image (working with the landmask only). Intented to be used as an abstract class providing common interface and methods 
class GlobalBuilder(TLSbase):
  #constructor
  def __init__(self, image, basemask, layermask, channelmask, mndst, multigen, *args):
    mwin = TLSbase.__init__(self, image, basemask, layermask, channelmask, mndst, *args)
    self.textes = None #this should be instantiated in child classes
    self.multigen = multigen

    #No GUI here, it is buildt in the child classes as it may change from class to class. Only the button area is buildt here, which should be equal for all the children
    #No button area

    return mwin

  #method adding the generate button
  def add_button_generate(self, btxt):
    self.butgenpr = gtk.Button(btxt)
    self.action_area.add(self.butgenpr)
    self.butgenpr.connect("clicked", self.on_butgen_clicked)

  #callback method acting on the generate button
  def on_butgen_clicked(self, widget):
    if self.generated and not self.multigen:
      self.cleandrawables()
    self.generatestep()
    self.setgenerated(True)
    if self.multigen:
      self.setbeforerun()


#class for building stuffs in small selected areas. Intented to be used as an abstract class providing common interface and methods (old BuildAddition class)
class LocalBuilder(TLSbase):
  #constructor
  def __init__(self, image, layermask, channelmask, multigen, *args):
    mwin = TLSbase.__init__(self, image, None, layermask, channelmask, False, *args)
    self.addingchannel = None
    self.textes = None #this should be instantiated in child classes
    self.multigen = multigen
    self.smoothbeforecomb = True
    
    self.allmasks = [] #will be list of lists
    self.childnames = ["base", "noise", "clip", "layer"]
    
    self.smoothbase = 0
    self.smoothlist = ["None", "Small", "Medium", "Big"]
    self.smoothvallist = None
    self.smoothval = 0 #will be reinitialized by the dedicated method
    
    #No GUI here, it is buildt in the child classes as it may change from class to class. Only the button area is buildt here, which should be equal for all the children
    #No button area

    return mwin

  #class holding the interface to delete paths
  class DelGroup(gtk.Dialog):
    #constructor
    def __init__(self, grouplist, *args):
      swin = gtk.Dialog.__init__(self, *args)
      self.set_border_width(10)
      self.glist = grouplist
      self.selgroup = -1

      #new row
      hbxa = gtk.HBox(spacing=10, homogeneous=True)
      self.vbox.add(hbxa)
      
      laba = gtk.Label("Select the name of the group you want to delete.")
      hbxa.add(laba)

      #new row
      hboxb = gtk.HBox(spacing=10, homogeneous=True)
      self.vbox.add(hboxb)
            
      boxmodelb = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT)
      groupsnames = ["All"] + [ll.name for ll in self.glist]
      groupsidx = [-1] + range(len(self.glist))
      
      #filling the model for the combobox
      for i, j in zip(groupsnames, groupsidx):
        irow = boxmodelb.append(None, [i, j])

      cboxb = gtk.ComboBox(boxmodelb)
      rendtextb = gtk.CellRendererText()
      cboxb.pack_start(rendtextb, True)
      cboxb.add_attribute(rendtextb, "text", 0)
      cboxb.set_entry_text_column(0)
      cboxb.set_active(0)
      cboxb.connect("changed", self.on_selgroup_changed)
      hboxb.add(cboxb)

      #button area
      self.add_button("Cancel", gtk.RESPONSE_CANCEL)
      self.add_button("OK", gtk.RESPONSE_OK)
      
      self.show_all()
      return swin

    #callback method to select the path to be deleted
    def on_selgroup_changed(self, widget):
      refmode = widget.get_model()
      self.selgroup = refmode.get_value(widget.get_active_iter(), 1)

    #method to get the selected path (vector and layer objects)
    def getselected(self):
      return self.selgroup

  #outer class methods
  #method adding the cancel button
  def add_button_cancel(self):
    self.butcanc = gtk.Button("Cancel")
    self.action_area.add(self.butcanc)
    self.butcanc.connect("clicked", self.on_butcanc_clicked)

  #method adding the random and handmade generate button
  def add_buttons_gen(self):
    self.butgenrnd = gtk.Button("Random")
    self.action_area.add(self.butgenrnd)
    self.butgenrnd.connect("clicked", self.on_butgenrdn_clicked)

    self.butgenhnp = gtk.Button("Hand-placed")
    self.action_area.add(self.butgenhnp)
    self.butgenhnp.connect("clicked", self.on_butgenhnp_clicked)

  #method, setting the smoothbeforecomb parameter
  def setsmoothbeforecomb(self, val):
    if isinstance(val, (bool)):
      self.smoothbeforecomb = val
  
  #method, setting and adding the smooth parameters and drawing the relative combobox
  def smoothdef(self, base, cblabtxt):
    #base should be a 3 element list with floating numbers representing the smooth size in percentage
    if len(base) != 3:
      raise TypeError("Error, first argument of LocalBuilder.smoothdef method must be a 3 element list, with numerical values.")
      
    self.smoothbase = [0] + base
    self.smoothvallist = [i * 0.5 * (self.img.width + self.img.height) for i in self.smoothbase]
    
    #adding first row to the GUI
    self.hbxsm = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(self.hbxsm)
    
    labsm = gtk.Label(cblabtxt)
    self.hbxsm.add(labsm)
    
    boxmodelsm = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT)
    
    #filling the model for the combobox
    for i, j in zip(self.smoothlist, self.smoothvallist):
      irow = boxmodelsm.append(None, [i, j])

    self.smoothval = self.smoothvallist[2]

    cboxsm = gtk.ComboBox(boxmodelsm)
    rendtextsm = gtk.CellRendererText()
    cboxsm.pack_start(rendtextsm, True)
    cboxsm.add_attribute(rendtextsm, "text", 0)
    cboxsm.set_entry_text_column(0)
    cboxsm.set_active(2)
    cboxsm.connect("changed", self.on_smooth_changed)
    self.hbxsm.add(cboxsm)
    
    #adding second row to the GUI
    self.hbxsc = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(self.hbxsc)
    
    self.chbsc = gtk.CheckButton("Prevent smoothing near the coast.")
    self.chbsc.set_active(self.smoothbeforecomb)
    self.chbsc.connect("toggled", self.on_chsc_toggled)
    self.hbxsc.add(self.chbsc)

  #appending channel mask to the list of list
  def appendmask(self, mask, newsublist=True):
    if newsublist:
      self.allmasks.append([mask])
    else:
      self.allmasks[-1].append(mask)
  
  #return channel masks generated by the object.
  def getallmasks(self):
    return [msk for ml in self.allmasks for msk in ml] #flattening the list
    
  #callback method, set the smooth parameter
  def on_smooth_changed(self, widget):
    refmode = widget.get_model()
    self.smoothval = refmode.get_value(widget.get_active_iter(), 1)

  #callback method, setting smooth_before parameter
  def on_chsc_toggled(self, widget):
    self.smoothbeforecomb = widget.get_active()

  #override cleaning method, common to all LocalBuild childs
  def cleandrawables(self):
    fuldr = self.groupl + self.getallmasks()
    self.deletedrawables(*fuldr)
    
  #override loading method, common to all LocalBuild childs
  def loaddrawables(self):
    self.loadgrouplayer(self.textes["baseln"] + "group")
    #we need to reverse the img.channel list, as the first mask we need to look for is the last in this list
    for ll in self.img.channels[::-1]: #working on a reversed list
      if any([i in ll.name for i in self.namelist]):
        self.appendmask(ll, self.namelist[0] in ll.name)
    self.allmasks.reverse() #reversing the list again to match the indexes with the group when deleting only one group
    return self.loaded()

  #callback method to cancel a single step
  def on_butcanc_clicked(self, widget):
    groupselecter = self.DelGroup(self.groupl, "Removing steps", self, gtk.DIALOG_MODAL)
    rr = groupselecter.run()

    if rr == gtk.RESPONSE_OK:
      grouptod = groupselecter.getselected()

      if grouptod == -1:
        self.cleandrawables()
        self.setgenerated(False)
        self.setbeforerun()
      else:
        #deleting the group
        pdb.gimp_image_remove_layer(self.img, self.groupl[grouptod])
        del self.groupl[grouptod]
        #deleting the channel masks
        chtodl = self.allmasks[grouptod]
        for mm in chtodl:
          pdb.gimp_image_remove_channel(self.img, mm)
        del self.allmasks[grouptod]

        if len(self.groupl) == 0:
          self.setgenerated(False)

      pdb.gimp_displays_flush()
    groupselecter.destroy()

  #callback method to generate random selection (mask profile)
  def on_butgenrdn_clicked(self, widget):
    if self.generated and not self.multigen:
      self.cleandrawables()
    self.makegrouplayer(self.textes["baseln"] + "group", 0)
    baselayer = self.makeunilayer(self.textes["baseln"] + "base")
    newmp = MaskProfile(self.textes, self.img, baselayer, self.maskl, self.getgroupl(), "Building " + self.textes["baseln"] + " mass", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    if self.smoothbeforecomb and self.smoothval > 0:
      newmp.setsmoothprof(self.smoothval)

    newmp.run()
    self.addingchannel = newmp.channelms
    self.addingchannel.name = self.textes["baseln"] + "mask"

    #hiding or removing not needed stuffs
    if newmp.chtype > 0:
      pdb.gimp_item_set_visible(newmp.bgl, False)
      pdb.gimp_item_set_visible(newmp.noisel, False)
      pdb.gimp_item_set_visible(newmp.clipl, False)
      pdb.gimp_item_set_visible(newmp.maskl, False)
      self.appendmask(self.addingchannel)
      self.generatestep()
      self.setgenerated(True)
      if self.multigen:
        self.setbeforerun()
    else:
      pdb.gimp_image_remove_layer(self.img, newmp.bgl)
      
  #callback method to let the user to select the area by hand and generate the mask profile.
  def on_butgenhnp_clicked(self, widget):
    if self.generated and not self.multigen:
      self.cleandrawables()

    #making the grouplayer
    if len(self.groupl) == 0:
      self.makegrouplayer(self.textes["baseln"] + "group", 0)
    elif len(self.getgroupl().layers) > 0:
      self.makegrouplayer(self.textes["baseln"] + "group", 0)
      
    #dialog telling to select the area where to place the stuff
    infodi = gtk.Dialog(title="Info", parent=self)
    imess = "Select the area where you want to place the "+ self.textes["labelext"] + " with the lazo tool or another selection tool.\n"
    imess += "When you have a selection, press Ok. Press Cancel to clear the current selection and start it again."
    ilabel = gtk.Label(imess)
    infodi.vbox.add(ilabel)
    ilabel.show()
    ichb = gtk.CheckButton("Intersect selection with land mass if present\n(prevent the sea from being covered by the new area.")
    ichb.set_active(True)
    infodi.vbox.add(ichb)
    ichb.show()
    infodi.add_button("Cancel", gtk.RESPONSE_CANCEL)
    infodi.add_button("Ok", gtk.RESPONSE_OK)
    diresp = infodi.run()

    if (diresp == gtk.RESPONSE_OK):
      if not pdb.gimp_selection_is_empty(self.img):
        if self.smoothbeforecomb and self.smoothval > 0:
          pdb.gimp_selection_feather(self.img, self.smoothval)
          
        self.addingchannel = pdb.gimp_selection_save(self.img)
        pdb.gimp_selection_none(self.img)
        #combining the new mask with the land profile
        if self.channelms is not None and ichb.get_active():
          pdb.gimp_channel_combine_masks(self.addingchannel, self.channelms, 3, 0, 0)
        infodi.destroy()
        self.addingchannel.name = self.textes["baseln"] + "mask"
        self.appendmask(self.addingchannel)
        self.generatestep()
        self.setgenerated(True)
        if self.multigen:
          self.setbeforerun()
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
          self.on_butgenhnp_clicked(widget)

    elif (diresp == gtk.RESPONSE_CANCEL):
      pdb.gimp_selection_none(self.img)
      infodi.destroy()
      self.on_butgenhnp_clicked(widget)


#class to generate random mask profile
class MaskProfile(GlobalBuilder):
  #constructor
  def __init__(self, textes, image, tdraw, basemask, grouplayer, *args):
    mwin = GlobalBuilder.__init__(self, image, basemask, None, None, True, False, *args)
    
    self.bgl = tdraw
    
    #internal arguments
    self.fsg = 10
    self.textes = textes
    self.groupl = grouplayer #overwriting groupl 
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
    self.add_button_generate("Generate profile")
     
    butn = gtk.Button("Next")
    self.action_area.add(butn)
    butn.connect("clicked", self.on_butnext_clicked)
    
    self.show_all()
    return mwin
  
  #nested class, handling a subdialog to improve choice for the mask
  class SettingDir(gtk.Dialog):
    #constructor
    def __init__(self, textes, *args):
      swin = gtk.Dialog.__init__(self, *args)
      self.set_border_width(10)
      
      self.textes = textes
      self.namelist = ["top", "top-right", "right", "bottom-right", "bottom", "bottom-left", "left", "top-left"]
      self.xlist = [1, 2, 2, 2, 1, 0, 0, 0]
      self.ylist = [0, 0, 1, 2, 2, 2, 1, 0]
      self.dx = 0 #will be reinitialized during GUI costruction  
      self.dy = 0 #will be reinitialized during GUI costruction
      
      #new row
      laba = gtk.Label(self.textes["topnestedlab"])
      self.vbox.add(laba)
      
      #new row
      boxmodelb = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT, gobject.TYPE_INT)
      
      #filling the model for the combobox
      for i, j, k in zip(self.namelist, self.xlist, self.ylist):
        irow = boxmodelb.append(None, [i, j, k])

      self.dx = self.xlist[0]
      self.dy = self.ylist[0]
      
      cboxb = gtk.ComboBox(boxmodelb)
      rendtextb = gtk.CellRendererText()
      cboxb.pack_start(rendtextb, True)
      cboxb.add_attribute(rendtextb, "text", 0)
      cboxb.set_entry_text_column(0)
      cboxb.set_active(0)
      cboxb.connect("changed", self.on_dir_changed)
      self.vbox.add(cboxb)
      
      #adding button with customized answers
      self.add_button("OK", gtk.RESPONSE_OK)
      
      self.show_all()
      return swin
  
    #callback method, setting the direction parameters
    def on_dir_changed(self, widget):
      refmode = widget.get_model()
      self.dx = refmode.get_value(widget.get_active_iter(), 1)
      self.dy = refmode.get_value(widget.get_active_iter(), 2)
  
  #methods of the outer class:
  #callback method, setting the coast type to the one in the combobox
  def on_type_changed(self, widget):
    refmode = widget.get_model()
    self.chtype = refmode.get_value(widget.get_active_iter(), 1)
  
  #callback method, regenerate the land profile
  def on_butnext_clicked(self, widget):
    if not self.generated:
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
  
  #override cleaning method
  def cleandrawables(self):
    self.deletedrawables(self.maskl, self.channelms)
  
  #override method, generate the profile
  def generatestep(self):
    if self.generated:
      self.bgl = self.makeunilayer(self.textes["baseln"] + "base", (255, 255, 255))
    else:
      self.bgl.name = self.textes["baseln"] + "base"
      
    #Using the TSL tecnnique: shape layer
    if (self.chtype == 0): #skip everything
      pass
    else:
      nn = False
      if (self.chtype == 1): #to generate multi-random area
        #setting the layer to a light gray color
        nn = True
        colfillayer(self.img, self.bgl, (128, 128, 128)) #rgb notation for a 50% gray
      elif (self.chtype > 1 and self.chtype < 5):
        if (self.chtype == 2): #to generate one-side area
          gradtype = 0 #linear
          seldir = self.SettingDir(self.textes, "Set position", self, gtk.DIALOG_MODAL) #initializate an object of type nested class
          rd = seldir.run()
          if rd == gtk.RESPONSE_OK:
            #setting the coordinates for gradient drawing
            if seldir.dx == 0:
              x1 = pdb.gimp_image_width(self.img) - (random.random() * (pdb.gimp_image_width(self.img) / self.fsg))
              x2 = random.random() * (pdb.gimp_image_width(self.img) / self.fsg)
            elif seldir.dx == 1:
              x1 = pdb.gimp_image_height(self.img)/2 + ((random.random() -0.5) * (pdb.gimp_image_height(self.img) / self.fsg))
              x2 = pdb.gimp_image_height(self.img)/2 + ((random.random() -0.5) * (pdb.gimp_image_height(self.img) / self.fsg))
            elif seldir.dx == 2:
              x1 = random.random() * (pdb.gimp_image_width(self.img) / self.fsg)
              x2 = pdb.gimp_image_width(self.img) - (random.random() * (pdb.gimp_image_width(self.img) / self.fsg))
              
            if seldir.dy == 0:
              y1 = pdb.gimp_image_height(self.img) - (random.random() * (pdb.gimp_image_height(self.img) / self.fsg))
              y2 = random.random() * (pdb.gimp_image_height(self.img) / self.fsg)
            elif seldir.dy == 1:
              y1 = pdb.gimp_image_height(self.img)/2 + ((random.random() -0.5) * (pdb.gimp_image_height(self.img) / self.fsg))
              y2 = pdb.gimp_image_height(self.img)/2 + ((random.random() -0.5) * (pdb.gimp_image_height(self.img) / self.fsg))
            elif seldir.dy == 2:
              y1 = random.random() * (pdb.gimp_image_height(self.img) / self.fsg)
              y2 = pdb.gimp_image_height(self.img) - (random.random() * (pdb.gimp_image_height(self.img) / self.fsg))
                          
            seldir.destroy()
          
        elif (self.chtype == 3 or self.chtype == 4): #to generate a circular area or corona
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
      self.noisel = self.makenoisel(self.textes["baseln"] + "noise", 5, 5, OVERLAY_MODE, False, nn)
      cmm = "The lower the selected value, the wider the affected area."
      self.clipl = self.makeclipl(self.textes["baseln"] + "clip", cmm)
      self.makeprofilel(self.textes["baseln"] + "layer")
      
      pdb.gimp_displays_flush()
      

#class to generate the water mass profile (sea, ocean, lakes)
class WaterBuild(GlobalBuilder):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    mwin = GlobalBuilder.__init__(self, image, None, layermask, channelmask, True, False, *args)
    self.seal = None
    self.shorel = None

    #internal parameters
    self.smoothnamelist = ["none", "small", "medium", "large"]
    self.smoothvallist = [0, 0.20, 0.40, 0.60] #is a percentage
    self.smoothpixlist = [i * 0.5 * (self.img.width + self.img.height) for i in self.smoothvallist]
    self.smooth = 0 #will be reinitialized in GUI costruction
    self.addshore = True
    
    self.colorwaterdeep = (37, 50, 95) #a deep blue color
    self.colorwaterlight = (241, 244, 253) #a very light blue color almost white

    self.namelist = ["seashape", "sea", "seashore"]

    #Designing the interface
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Smoothing parameter for water deepness")
    hbxa.add(laba)
    
    boxmodela = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT)
    #filling the model for the combobox
    for i, j in zip(self.smoothnamelist, self.smoothpixlist):
      irow = boxmodela.append(None, [i, j])

    self.smooth = self.smoothpixlist[1]

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
    self.add_button_quit()
    self.add_button_generate("Generate water profile")
    self.add_button_nextprev()

    return mwin
    
  #callback method, setting smooth parameter
  def on_smooth_type_changed(self, widget):
    refmode = widget.get_model()
    self.smooth = refmode.get_value(widget.get_active_iter(), 1)
  
  #callback method, setting shore parameter
  def on_chb_toggled(self, widget):
    self.addshore = widget.get_active()
  
  #override cleaning method
  def cleandrawables(self):
    self.deletedrawables(self.seal, self.shorel)    

  #override loading method
  def loaddrawables(self):
    for ll in self.img.layers:
      if ll.name == self.namelist[0]:
        self.bgl = ll
      if ll.name == self.namelist[1]:
        self.seal = ll
      if ll.name == self.namelist[2]:
        self.shorel = ll
    return self.loaded()
        
  #override method, generate water profile
  def generatestep(self):
    #getting bgl as copy of land mask
    self.copybgl(self.maskl, "seashape")

    if (self.smooth > 0):
      pdb.plug_in_gauss(self.img, self.bgl, self.smooth, self.smooth, 0)
      pdb.gimp_displays_flush()
    
    self.noisel = self.makenoisel("seanoise", 4, 4, OVERLAY_MODE)
    self.bgl = pdb.gimp_image_merge_down(self.img, self.noisel, 0)

    #copy bgl layer into a new layer 
    self.seal = self.bgl.copy()
    self.seal.name = "sea"
    pdb.gimp_image_insert_layer(self.img, self.seal, self.getgroupl(), 0)
    
    self.addmaskp(self.seal, self.channelms, True, True)
    pdb.plug_in_normalize(self.img, self.seal)
    pdb.gimp_image_select_item(self.img, 2, self.seal) #this selects the non transparent region of the layer, #2 = replace selection
    pdb.gimp_selection_invert(self.img) #inverting the selection
    colfillayer(self.img, self.seal, (255, 255, 255)) #filling selected area with white
    pdb.gimp_selection_none(self.img)

    #smoothing near the coast and apply color
    pdb.plug_in_gauss(self.img, self.seal, 20, 20, 0)
    self.cgradmap(self.seal, self.colorwaterdeep, self.colorwaterlight)
    
    #adding shore
    if (self.addshore):
      self.shorel = self.makeunilayer("seashore", self.colorwaterlight)
      maskshore = self.addmaskp(self.shorel)
      pxpar = 0.01 * (self.img.width + self.img.height)/2.0
      if (pxpar < 5):
        pxpar = 5.0
      
      pdb.plug_in_gauss(self.img, maskshore, pxpar, pxpar, 0)
    
    pdb.gimp_displays_flush()


class RegionChooser:
  #constructor
  def __init__(self):
    #@@@ ideally all of these: grassland, terrain, desert, arctic, underdark || these should be smaller regions rendered in other ways: forest, mountain, swamp
    self.regionlist = ["grassland", "terrain", "desert", "arctic", "custom color map"]
    self.regiontype = ["grass", "ground", "sand", "ice", "custom"]
    self.region = self.regiontype[0] #will be reinitialized in GUI costruction

  def addchooserrow(self):
    #new row
    hobox = gtk.HBox(spacing=10, homogeneous=True)
    
    laba = gtk.Label("Select type of region")
    hobox.add(laba)
    
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
    hobox.add(cboxa)
    return hobox

  #callback method, setting base region parameter 
  def on_region_changed(self, widget):
    refmode = widget.get_model()
    self.region = refmode.get_value(widget.get_active_iter(), 1)


#class to generate the base land (color and mask of the terrain)
class BaseDetails(GlobalBuilder, RegionChooser):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    RegionChooser.__init__(self)
    mwin = GlobalBuilder.__init__(self, image, None, layermask, channelmask, True, False, *args)
    self.bumpmapl = None
    self.basebumpsl = None
    self.refbg = None

    self.colorref = colordict
    smtextes = {"baseln" : "smallregion", \
    "labelext" : "small colored area", \
    "namelist" : ["none", "random", "one side", "centered", "surroundings", "customized"], \
    "toplab" : "In the final result: white represent where the new areas are located.", \
    "topnestedlab" : "Position of the new area in the image."}
    self.localbuilder = AdditionalDetBuild(smtextes, self.img, self.maskl, self.channelms, "Building smaller areas", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    
    self.choserbox = self.addchooserrow()
    self.vbox.add(self.choserbox)
    
    self.namelist = [self.regiontype, [n + "texture" for n in self.regiontype], [n + "bumpmap" for n in self.regiontype], [n + "bumps" for n in self.regiontype]]
    
    #button area
    self.add_button_quit()
    self.add_button_generate("Generate land details")

    self.butlocal = gtk.Button("Local areas")
    self.action_area.add(self.butlocal)
    self.butlocal.connect("clicked", self.on_local_clicked)

    self.add_button_nextprev()

    return mwin
    
  #callback method, showing interface to add local areas 
  def on_local_clicked(self, widget):
    if self.generated:
      self.localbuilder.show_all()
      self.localbuilder.run()

  #override cleaning method
  def cleandrawables(self):
    self.deletedrawables(self.bumpmapl, self.basebumpsl)
    self.localbuilder.cleandrawables()

  #ovverride loading method
  def loaddrawables(self):
    for ll in self.img.layers:
      if ll.name in self.namelist[0]:
        self.bgl = ll
      elif ll.name in self.namelist[1]:
        self.noisel = ll
      elif ll.name in self.namelist[2]:
        self.bumpmapl = ll
      elif ll.name in self.namelist[3]:
        self.basebumpsl = ll

    self.localbuilder.loaddrawables()
    return self.loaded()
    
  #override method, generate land details
  def generatestep(self):    
    #getting bgl as copy of water bgl (we have a WaterBuild instance) or the first background layer
    if isinstance(self.refbg, WaterBuild):
      self.copybgl(self.refbg.bgl, "base")
    else:
      self.copybgl(self.refbg, "base")

    #setting base color
    self.addmaskp(self.bgl)
    self.bgl.name = self.region
    if self.bgl.name == "custom":
      cmapper = ColorMapper("Choose a light and deep color at the edge of a gradient map", True, "Color chooser", self, gtk.DIALOG_MODAL)
      rr = cmapper.run()
      if rr == gtk.RESPONSE_OK:
        self.cgradmap(self.bgl, cmapper.chcol["deep"],  cmapper.chcol["light"])
      cmapper.destroy()
    else:
      self.cgradmap(self.bgl, self.colorref[self.bgl.name]["deep"], self.colorref[self.bgl.name]["light"])
      
    pdb.gimp_displays_flush()
    
    #adding small areas of other region types
    self.localbuilder.show_all()
    self.localbuilder.setbgl(self.bgl)
    self.localbuilder.run()

    #generating noise
    self.noisel = self.makenoisel(self.bgl.name + "texture", 3, 3, OVERLAY_MODE)
    self.addmaskp(self.noisel)
    
    #create an embossing effect using a bump map
    self.bumpmapl = self.makenoisel(self.bgl.name + "bumpmap", 15, 15, NORMAL_MODE, True)
    pdb.gimp_item_set_visible(self.bumpmapl, False)
    self.basebumpsl = self.makeunilayer(self.bgl.name + "bumps", (128, 128, 128))
    pdb.gimp_layer_set_mode(self.basebumpsl, OVERLAY_MODE)

    pdb.plug_in_bump_map_tiled(self.img, self.basebumpsl, self.bumpmapl, 120, 45, 3, 0, 0, 0, 0, True, False, 2) #2 = sinusoidal
    self.addmaskp(self.basebumpsl)

    pdb.gimp_displays_flush()
    

#class to generate small area of a different land type than the main one
class AdditionalDetBuild(LocalBuilder, RegionChooser):
  #constructor
  def __init__(self, textes, image, layermask, channelmask, *args):
    RegionChooser.__init__(self)
    mwin = LocalBuilder.__init__(self, image, layermask, channelmask, True, *args)

    self.refbase = None
    self.textes = textes
    self.colorref = colordict
    self.namelist = [self.textes["baseln"] + "mask"]
    
    #Designing the interface
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Adding / deleting " + self.textes["labelext"] + " to the map.")
    hbxa.add(laba)

    self.choserbox = self.addchooserrow()
    self.vbox.add(self.choserbox)
    
    #new row
    self.smoothdef([0.03, 0.06, 0.1], "Select smoothing range for the area,\nit helps the blending with the main color.")
    
    #button area
    self.add_button_quit()
    self.add_button_cancel()
    self.add_buttons_gen()

    return mwin
    
  #override method, drawing the area
  def generatestep(self):
    self.copybgl(self.refbase, self.textes["baseln"])
    
    #setting the color
    if self.region == "custom":
      cmapper = ColorMapper("Choose a light and deep color at the edge of a gradient map", True, "Color chooser", self, gtk.DIALOG_MODAL)
      rr = cmapper.run()
      if rr == gtk.RESPONSE_OK:
        self.cgradmap(self.bgl, cmapper.chcol["deep"],  cmapper.chcol["light"])
      cmapper.destroy()
    else:
      self.cgradmap(self.bgl, self.colorref[self.region]["deep"], self.colorref[self.region]["light"])

    if pdb.gimp_layer_get_mask(self.bgl) is not None:
      pdb.gimp_layer_remove_mask(self.bgl, 1) #1 = MASK_DISCARD

    maskt = self.addmaskp(self.bgl, self.addingchannel)
    if not self.smoothbeforecomb and self.smoothval > 0:
      pdb.plug_in_gauss(self.img, maskt, self.smoothval, self.smoothval, 0)

    pdb.gimp_displays_flush()

  #setting a reference to the base layer, to be called before a run, but not everytime we generated a step (so we cannot use setbeforerun method)
  def setbgl(self, basel):
    self.refbase = basel


#class to generate the dirt on the terrain
class DirtDetails(GlobalBuilder):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    mwin = GlobalBuilder.__init__(self, image, None, layermask, channelmask, False, False, *args)
    self.smp = 50
    self.regtype = None
    self.namelist = ["dirt", "dirtnoise"]
        
    #colors
    self.colordirt = (128, 107, 80) #med dirt, a moderate brown

    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    laba = gtk.Label("Adding dirt to the map. If you do not want to draw dirt, just press Next.")
    hbxa.add(laba)
    
    #button area
    self.add_button_quit()
    self.add_button_generate("Generate dirt")
    self.add_button_nextprev()

    return mwin

  #method to make the more complex noise for dirt: should be combined with the land profile to have dirt close to the coast if a coast is present
  def makedirtnoisel(self, lname, pixsize):
    #preparing the noiselayer generation
    if self.maskl is not None:
      masklcopy = self.maskl.copy()
      pdb.gimp_image_insert_layer(self.img, masklcopy, self.getgroupl(), 0)
      pdb.plug_in_gauss(self.img, masklcopy, self.smp, self.smp, 0)
    
      #adding the noise layer mixed with the copy mask
      self.noisel = self.makenoisel(lname, pixsize, pixsize, DIFFERENCE_MODE)
      self.noisel = pdb.gimp_image_merge_down(self.img, self.noisel, 0)
      pdb.gimp_invert(self.noisel)
      
    else:
      #just generating a normal noise layer
      self.noisel = self.makenoisel(lname, pixsize, pixsize, NORMAL_MODE)
      
    #correcting the mask color levels
    commtxt = "Set minimum, maximum and gamma to edit the B/W ratio in the image.\n"
    commtxt += "The white regions will be covered by dirt."
    cld = CLevDialog(self.img, self.noisel, commtxt, CLevDialog.LEVELS, [CLevDialog.INPUT_MIN, CLevDialog.GAMMA, CLevDialog.INPUT_MAX], self.getgroupl(), "Set input levels", self, gtk.DIALOG_MODAL)
    cld.run()
    resl = cld.reslayer
    cld.destroy()
    return resl

  #override cleaning method
  def cleandrawables(self):
    self.deletedrawables()

  #ovverride loading method
  def loaddrawables(self):
    for ll in self.img.layers:
      if ll.name == self.namelist[0]:
        self.bgl = ll
      elif ll.name == self.namelist[1]:
        self.noisel = ll
    return self.loaded()

  #override method, generate the layers to create the dirt
  def generatestep(self):
    self.bgl = self.makeunilayer("bgl", self.colordirt)
    self.bgl.name = "dirt"
    
    #adding some effect to the layer to make it like dirt
    pdb.plug_in_hsv_noise(self.img, self.bgl, 4, 11, 10, 22)
    pdb.plug_in_bump_map_tiled(self.img, self.bgl, self.bgl, 120, 45, 3, 0, 0, 0, 0, True, False, 2) #2 = sinusoidal
    
    self.noisel = self.makedirtnoisel("dirtnoise", 16)
    
    #applying some masks
    self.addmaskp(self.bgl, self.channelms, False, True)
    maskbis = self.addmaskp(self.bgl) #readding but not applying, we need to work on the second mask

    noisemask = self.addmaskp(self.noisel)
    pdb.plug_in_gauss(self.img, self.noisel, 10, 10, 0)
    pdb.plug_in_spread(self.img, self.noisel, 10, 10)    
    self.addmaskp(self.noisel) #here called again to apply the mask
    
    #applying the mask, final step
    if self.maskl is not None:
      masklcopy = self.maskl.copy()
      pdb.gimp_image_insert_layer(self.img, masklcopy, self.getgroupl(), 1)      
      self.noisel = pdb.gimp_image_merge_down(self.img, self.noisel, 0)

    self.noisel.name = "dirtnoise"
    pdb.gimp_edit_copy(self.noisel)
    flsel = pdb.gimp_edit_paste(maskbis, False)
    pdb.gimp_floating_sel_anchor(flsel)

    pdb.gimp_item_set_visible(self.noisel, False)
    cldo = CLevDialog(self.img, self.bgl, "Set dirt opacity", CLevDialog.OPACITY, [], self.getgroupl(), "Set opacity", self, gtk.DIALOG_MODAL)
    cldo.run()
    cldo.destroy()
    
    pdb.gimp_displays_flush()


#class to generate the mountains
class MountainsBuild(LocalBuilder):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    mwin = LocalBuilder.__init__(self, image, layermask, channelmask, True, *args)
    self.base = None
    self.mntangularl = None
    self.cpvlayer = None
    self.embosslayer = None
    self.noisemask = None
    self.finalmaskl = None
    self.mntcolorl = None
    self.mntshadowl = None
    self.mntedgesl = None
    
    self.addsnow = True
    self.addcol = False
    self.addshadow = True
    self.raisedge = {"Top" : True, "Right" : True, "Bottom" : True, "Left" : True}
    
    self.setsmoothbeforecomb(False) #mountains should always be smoothed later
    
    self.textes = {"baseln" : "mountains", \
    "labelext" : "mountains", \
    "namelist" : ["no mountains", "sparse", "mountain border", "central mountain mass", "central valley", "customized"], \
    "toplab" : "In the final result: white represent where mountains are drawn.", \
    "topnestedlab" : "Position of the mountains masses in the image."}

    finalnames = ["mask", "defmask"]
    self.namelist = [self.textes["baseln"] + fn for fn in finalnames]
    
    #Designing the interface
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)

    labatxt = "Adding mountains to the map. If you do not want to draw mountains, just press Next.\n"
    labatxt += "You can repeat the step multiple times: just press again one of the buttons to repeat the process and add new mountains."
    laba = gtk.Label(labatxt)
    hbxa.add(laba)
    
    #new row
    self.smoothdef([0.03, 0.1, 0.2], "Select smoothing for mountains feet.")
    
    #new row
    hbxd = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxd)
    chbd = gtk.CheckButton("Colour mountains.")
    chbd.set_active(self.addcol)
    chbd.connect("toggled", self.on_chbd_toggled)
    hbxd.add(chbd)
    
    #new row
    hbxb = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxb)
    chbb = gtk.CheckButton("Add snow on mountain's top.")
    chbb.set_active(self.addsnow)
    chbb.connect("toggled", self.on_chbb_toggled)
    hbxb.add(chbb)

    #new row
    hbxe = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxe)
    chbe = gtk.CheckButton("Add shadow at mountains' feet.")
    chbe.set_active(self.addshadow)
    chbe.connect("toggled", self.on_chbe_toggled)
    hbxe.add(chbe)

    #new row
    hbxf = gtk.HBox(spacing=3, homogeneous=False)
    self.vbox.add(hbxf)
    labf = gtk.Label("Raise mountains on image borders:")
    hbxf.add(labf)
    chbfa = self.addingchbegde(self.raisedge.keys()[0])
    hbxf.add(chbfa)
    chbfb = self.addingchbegde(self.raisedge.keys()[1])
    hbxf.add(chbfb)
    chbfc = self.addingchbegde(self.raisedge.keys()[2])
    hbxf.add(chbfc)
    chbfd = self.addingchbegde(self.raisedge.keys()[3])
    hbxf.add(chbfd)
    
    #button area
    self.add_button_quit()
    self.add_button_cancel()
    self.add_buttons_gen()
    self.add_button_nextprev()

    return mwin

  #adding a checkbutton for rasing the mountains at image borders
  def addingchbegde(self, dictkey):
    chbt = gtk.CheckButton(dictkey)
    chbt.set_active(self.raisedge[dictkey])
    chbt.connect("toggled", self.on_chbfany_toggled, dictkey)
    return chbt
  
  #nested class to let the user control if the mountains mask should be improved and rotated
  class ControlMask(gtk.Dialog):
    #constructor
    def __init__(self, *args):
      swin = gtk.Dialog.__init__(self, *args)
      self.set_border_width(10)
      
      self.rotangle = 0
      
      #new row
      labtxt = "Overwrite mountain mask profile to create relatively narrow mountains chains in a wide selected area?\n"
      labtxt += "Mountains chains are oriented in the direction of the angle (in degrees).\n"
      labtxt += "0 is vertical, clockwise rotation up to 180 degrees allowed."
      laba = gtk.Label(labtxt)
      self.vbox.add(laba)
      
      #new row
      hbx = gtk.HBox(spacing=10, homogeneous=True)
      self.vbox.add(hbx)

      angleadj = gtk.Adjustment(self.rotangle, 0, 180, 1, 10)
      
      labb = gtk.Label("Set angle (degrees)")
      hbx.add(labb)
      
      scab = gtk.HScale(angleadj)
      scab.connect("value-changed", self.on_angle_changed)
      hbx.add(scab)
      
      spbutb = gtk.SpinButton(angleadj, 0, 2)
      spbutb.connect("output", self.on_angle_changed)
      hbx.add(spbutb)
      
      #button area
      self.add_button("No", gtk.RESPONSE_CANCEL)
      self.add_button("Yes", gtk.RESPONSE_OK)
      
      self.show_all()
      return swin
      
    #callback method, set the angle value (degrees)
    def on_angle_changed(self, widget):
      self.rotangle = widget.get_value()
    
    #get angle in radians
    def getanglerad(self):
      return (self.rotangle/180.0)*math.pi

  #nested class to let the user choosing the mountains color
  class ControlColor(gtk.Dialog):
    #constructor
    def __init__(self, *args):
      swin = gtk.Dialog.__init__(self, *args)
      self.set_border_width(10)

      self.colornames = ["Brown", "Gray", "Custom"]
      self.colorslight = [rgbcoltogdk(75, 62, 43), rgbcoltogdk(84, 84, 84), None] 
      self.colorsdeep = [rgbcoltogdk(167, 143, 107), rgbcoltogdk(207, 207, 207), None] 
      self.clight = gdkcoltorgb(self.colorslight[0])
      self.cdeep = gdkcoltorgb(self.colorsdeep[0])
      
      #new row
      labtxt = "Set mountains color from a predetermined list. Choose 'custom' to set arbitrary the colors."
      laba = gtk.Label(labtxt)
      self.vbox.add(laba)
   
      #new row            
      boxmodelb = gtk.TreeStore(gobject.TYPE_STRING, gtk.gdk.Color, gtk.gdk.Color)
      
      #filling the model for the combobox
      for i, j, k in zip(self.colornames, self.colorslight, self.colorsdeep):
        irow = boxmodelb.append(None, [i, j, k])

      self.sclight = gdkcoltorgb(self.colorslight[0])
      self.cdeep = gdkcoltorgb(self.colorsdeep[0])

      cboxb = gtk.ComboBox(boxmodelb)
      rendtextb = gtk.CellRendererText()
      cboxb.pack_start(rendtextb, True)
      cboxb.add_attribute(rendtextb, "text", 0)
      cboxb.set_entry_text_column(0)
      cboxb.set_active(0)
      cboxb.connect("changed", self.on_color_changed)
      self.vbox.add(cboxb)

      #button area
      self.add_button("Cancel", gtk.RESPONSE_CANCEL)
      okbutton = self.add_button("Ok", gtk.RESPONSE_OK)
      okbutton.connect("clicked", self.on_ok_clicked)

      self.show_all()
      return swin

    #callback method, setting the colors
    def on_color_changed(self, widget):
      refmode = widget.get_model()
      cll = refmode.get_value(widget.get_active_iter(), 1)
      cdd = refmode.get_value(widget.get_active_iter(), 2)

      if cll is not None and cdd is not None:
        self.clight = gdkcoltorgb(cll)
        self.cdeep = gdkcoltorgb(cdd)
      else:
        self.clight = None
        self.cdeep = None

    #callback method of the ok button, to allow the user to set a custom color if the custom option has been chosen
    def on_ok_clicked(self, widget):
      if self.clight is None or self.cdeep is None:
        cmapper = ColorMapper("Choose a light and deep color at the edge of a gradient map", True, "Color chooser", self, gtk.DIALOG_MODAL)
        rr = cmapper.run()
        if rr == gtk.RESPONSE_OK:
          self.clight = cmapper.chcol["light"]
          self.cdeep = cmapper.chcol["deep"]
        elif rr == gtk.RESPONSE_CANCEL:
          self.clight = (0, 0, 0)
          self.cdeep = (255, 255, 255)
        cmapper.destroy()

  #outer class methods:
  #callback method, set the adding snow variable
  def on_chbb_toggled(self, widget):
    self.addsnow = widget.get_active()

  #callback method, set the color variable
  def on_chbd_toggled(self, widget):
    self.addcol = widget.get_active()

  #callback method, set the adding shadow variable
  def on_chbe_toggled(self, widget):
    self.addshadow = widget.get_active()

  #callback method, set the raisedge value of k entry
  def on_chbfany_toggled(self, widget, k):
    self.raisedge[k] = widget.get_active()
            
  #override method, drawing the mountains in the selection (when the method is called, a selection channel for the mountains should be already present)
  def generatestep(self):    
    #improving the mask
    ctrlm = self.ControlMask()
    chrot = ctrlm.run()
    
    if chrot == gtk.RESPONSE_OK:
      rang = ctrlm.getanglerad()
      ctrlm.destroy()
      self.noisemask = self.makerotatedlayer(True, rang, self.makenoisel, (self.textes["baseln"] + "basicnoise", 6, 2, NORMAL_MODE, True, True))
      if self.smoothbeforecomb and self.smoothval > 0:
        masksmooth = 0
      else:
        masksmooth = self.smoothval
        
      self.finalmaskl, self.addingchannel = self.overdrawmask(self.noisemask, self.textes["baseln"], masksmooth, self.addingchannel, True, True)
      self.appendmask(self.addingchannel, False)
    elif chrot == gtk.RESPONSE_CANCEL:
      ctrlm.destroy()

    if len(self.groupl) == 1:
      self.base = pdb.gimp_layer_new_from_visible(self.img, self.img, self.textes["baseln"] + "mapbasehidden")
    basebis = self.base.copy()
    basebis.name = self.textes["baseln"] + "mapbase"
    pdb.gimp_image_insert_layer(self.img, basebis, self.getgroupl(), 0)
    maskbase = self.addmaskp(basebis, self.addingchannel)
    if self.smoothval > 0:
      pdb.plug_in_gauss(self.img, maskbase, self.smoothval, self.smoothval, 0)
    else:
      pdb.plug_in_gauss(self.img, maskbase, self.smoothvallist[1], self.smoothvallist[1], 0) #here always setting a bit of smooth on the map
    
    #creating blurred base
    self.bgl = self.makeunilayer(self.textes["baseln"] + "blur", (0, 0, 0))
    pdb.gimp_image_select_item(self.img, 2, self.addingchannel)
    colfillayer(self.img, self.bgl, (255, 255, 255))
    pdb.gimp_selection_none(self.img)
    if self.smoothval > 0:
      pdb.plug_in_gauss(self.img, self.bgl, self.smoothval, self.smoothval, 0)

    #creating noise
    self.noisel = self.makeunilayer(self.textes["baseln"] + "widenoise", (0, 0, 0))
    pdb.gimp_image_select_item(self.img, 2, self.addingchannel)
    if self.smoothval > 0:
      pdb.gimp_selection_feather(self.img, self.smoothval)
    paramstr = str(random.random() * 9999999999)
    paramstr += " 10.0 10.0 8.0 2.0 0.30 1.0 0.0 planar lattice_noise NO ramp fbm smear 0.0 0.0 0.0 fg_bg"
    try:
      pdb.plug_in_fimg_noise(self.img, self.noisel, paramstr) #using felimage plugin
    except:
      pdb.plug_in_solid_noise(self.img, self.noisel, False, False, random.random() * 9999999999, 16, 4, 4)
    
    #creating angular gradient
    self.mntangularl = self.makeunilayer(self.textes["baseln"] + "angular", (0, 0, 0))
    #drawing the gradients: #0 (first) = normal mode, 0 (second) linear gradient, 6 (third): shape angular gradient, True (eighth): supersampling
    pdb.gimp_edit_blend(self.mntangularl, 0, 0, 6, 100, 0, 0, True, True, 4, 3.0, True, 0, 0, self.img.width, self.img.height)

    #creating linear gradient to rise mountains on image edges
    self.mntedgesl = self.makeunilayer(self.textes["baseln"] + "edges", (0, 0, 0))
    for edg in self.raisedge.keys():
      if self.raisedge[edg]:
        tempedgel = self.makeunilayer(self.textes["baseln"] + "edges", (0, 0, 0))
        pdb.gimp_layer_set_mode(tempedgel, LIGHTEN_ONLY_MODE)
        #drawing the gradients: #0 (first) = normal mode, 0 (second) linear gradient, 6 (third): shape angular gradient, True (eighth): supersampling
        if edg == "Top":
          pdb.gimp_edit_blend(tempedgel, 0, 0, 0, 100, 0, 0, True, True, 4, 3.0, True, self.img.width/2, 0, self.img.width/2, self.img.height/4)
        elif edg == "Left":
          pdb.gimp_edit_blend(tempedgel, 0, 0, 0, 100, 0, 0, True, True, 4, 3.0, True, 0, self.img.height/2, self.img.width/4, self.img.height/2)
        elif edg == "Bottom":
          pdb.gimp_edit_blend(tempedgel, 0, 0, 0, 100, 0, 0, True, True, 4, 3.0, True, self.img.width/2, self.img.height, self.img.width/2, self.img.height * 0.75)
        elif edg == "Right":
          pdb.gimp_edit_blend(tempedgel, 0, 0, 0, 100, 0, 0, True, True, 4, 3.0, True, self.img.width, self.img.height/2, self.img.width * 0.75, self.img.height/2)
        self.mntedgesl = pdb.gimp_image_merge_down(self.img, tempedgel, 0)
        
    pdb.gimp_selection_none(self.img)
    
    #editing level modes and color levels
    pdb.gimp_layer_set_mode(self.noisel, ADDITION_MODE)
    pdb.gimp_layer_set_mode(self.mntangularl, ADDITION_MODE)
    pdb.gimp_layer_set_mode(self.mntedgesl, ADDITION_MODE)
    pdb.gimp_levels(self.bgl, 0, 0, 255, 1.0, 0, 85) #regulating color levels, channel = #0 (second parameter) is for histogram value
    inhh = self.get_brightness_max(self.noisel)
    pdb.gimp_levels(self.noisel, 0, 0, inhh, 1.0, 0, 50) #regulating color levels, channel = #0 (second parameter) is for histogram value
    pdb.gimp_levels(self.mntedgesl, 0, 0, 255, 1.0, 0, 100) #regulating color levels, channel = #0 (second parameter) is for histogram value
    pdb.gimp_levels(self.mntedgesl, 0, 0, 255, 1.0, 0, 100) #regulating color levels, channel = #0 (second parameter) is for histogram value
    
    #editing color curves
    ditext = "Try to eliminate most of the brightness by lowering the top-right control point\nand adding other points at the level of the histogram counts."
    cdd = CCurveDialog(self.img, self.mntangularl, self.getgroupl(), ditext, "Setting color curve", self, gtk.DIALOG_MODAL)
    cdd.run()
    self.mntangularl = cdd.reslayer
    
    self.cpvlayer = pdb.gimp_layer_new_from_visible(self.img, self.img, self.textes["baseln"] + "visible")
    pdb.gimp_image_insert_layer(self.img, self.cpvlayer, self.getgroupl(), 0)
    cdd.destroy()
    
    #editing color curves, again
    ditextb = "Try to add one or more control points below the diagonal\nin order to better define mountains peaks."
    cddb = CCurveDialog(self.img, self.cpvlayer, self.getgroupl(), ditextb, "Setting color curve", self, gtk.DIALOG_MODAL)
    cddb.run()
    self.cpvlayer = cddb.reslayer
    
    #adding mountains color
    if self.addcol:
      self.mntcolorl = cddb.reslayer.copy()
      self.mntcolorl.name = self.textes["baseln"] + "colors"
      pdb.gimp_image_insert_layer(self.img, self.mntcolorl, self.getgroupl(), 0)
      ctrlcl = self.ControlColor()
      rr = ctrlcl.run()
      if rr == gtk.RESPONSE_OK:
        self.cgradmap(self.mntcolorl, ctrlcl.clight, ctrlcl.cdeep)
      ctrlcl.destroy()
      maskcol = self.addmaskp(self.mntcolorl, self.addingchannel)
      if self.smoothval > 0:
        pdb.plug_in_gauss(self.img, maskcol, self.smoothval, self.smoothval, 0)
      else:
        pdb.plug_in_gauss(self.img, maskcol, self.smoothvallist[1], self.smoothvallist[1], 0) #here always setting a bit of smooth on the map
      
      pdb.gimp_item_set_visible(self.mntcolorl, False)
      
    #adding emboss effect
    self.embosslayer = cddb.reslayer.copy()
    self.embosslayer.name = self.textes["baseln"] + "emboss"
    pdb.gimp_image_insert_layer(self.img, self.embosslayer, self.getgroupl(), 0)
    cddb.destroy()
    pdb.plug_in_emboss(self.img, self.embosslayer, 30.0, 30.0, 20.0, 1)
    
    #fixing outside selection
    pdb.gimp_image_select_item(self.img, 2, self.addingchannel)
    if self.smoothval > 0:
      pdb.gimp_selection_feather(self.img, self.smoothval)
    pdb.gimp_selection_invert(self.img) #inverting selection
    colfillayer(self.img, self.embosslayer, (128, 128, 128))
    
    #drop shadow around the mountains
    if self.addshadow:
      pdb.plug_in_colortoalpha(self.img, self.embosslayer, (128, 128, 128))
      pdb.script_fu_drop_shadow(self.img, self.embosslayer, 2, 2, 15, (0, 0, 0), 75, False)
      self.mntshadowl = [i for i in self.getgroupl().layers if i.name == "Drop Shadow"][0]
      self.mntshadowl.name = self.textes["baseln"] + "shadow"
    
    #hiding not needed layers
    pdb.gimp_item_set_visible(self.bgl, False)
    pdb.gimp_item_set_visible(self.noisel, False)
    pdb.gimp_item_set_visible(self.mntangularl, False)
    pdb.gimp_item_set_visible(self.cpvlayer, False)
    pdb.gimp_item_set_visible(self.mntedgesl, False)
    pdb.gimp_layer_set_mode(self.embosslayer, OVERLAY_MODE)
    pdb.gimp_selection_none(self.img)

    #adding snow
    if self.addsnow:
      pdb.gimp_item_set_visible(self.cpvlayer, True)
      pdb.gimp_layer_set_mode(self.cpvlayer, SCREEN_MODE)
      commtxt = "Set minimum threshold to regulate the amount of the snow."
      cldc = CLevDialog(self.img, self.cpvlayer, commtxt, CLevDialog.THRESHOLD, [CLevDialog.THR_MIN], self.getgroupl(), "Set lower threshold", self, gtk.DIALOG_MODAL)
      cldc.run()
      self.cpvlayer = cldc.reslayer
      pdb.plug_in_gauss(self.img, self.cpvlayer, 5, 5, 0)
      pdb.gimp_layer_set_opacity(self.cpvlayer, 65)
      cldc.destroy()
      if self.addcol:
        pdb.gimp_image_raise_item(self.img, self.cpvlayer)
    
    if self.addcol:
      pdb.gimp_item_set_visible(self.mntcolorl, True)
      cldo = CLevDialog(self.img, self.mntcolorl, "Set mountains color opacity", CLevDialog.OPACITY, [], self.getgroupl(), "Set opacity", self, gtk.DIALOG_MODAL)
      cldo.run()
      cldo.destroy()

    pdb.gimp_displays_flush()


#class to generate the forests
class ForestBuild(LocalBuilder):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    mwin = LocalBuilder.__init__(self, image, layermask, channelmask, True, *args)
    self.shapelayer = None
    self.bumplayer = None
    self.forestshadow = None
    self.colorlayers = []
    
    self.browncol = {"tcbrown" : (75, 66, 47)}
    self.greencol = {"tcgreen" : (59, 88, 14)}
    self.yellowcol = {"tcyellow" : (134, 159, 48)}
    
    self.textes = {"baseln" : "forests", \
    "labelext" : "forests or woods", \
    "namelist" : ["no forests", "sparse woods", "big on one side", "big central wood", "surrounding", "customized"], \
    "toplab" : "In the final result: white represent where forests are drawn.", \
    "topnestedlab" : "Position of the area covered by the forest in the image."}
    finalnames = ["mask", "defmask"]
    self.namelist = [self.textes["baseln"] + fn for fn in finalnames]
    
    #Designing the interface
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)

    labatxt = "Adding forests to the map. If you do not want to draw forests, just press Next.\n"
    labatxt += "You can repeat the step multiple times: just press again one of the buttons to repeat the process and add new forests."
    laba = gtk.Label(labatxt)
    hbxa.add(laba)
    
    #button area
    self.add_button_quit()
    self.add_button_cancel()
    self.add_buttons_gen()
    self.add_button_nextprev()
    
    return mwin
    
  #method to add a masked layer color
  def addforestcol(self, fc):
    lab = fc.keys()[0]
    resl = self.makeunilayer(self.textes["baseln"] + lab, fc[lab])
    self.addmaskp(resl, self.addingchannel)
    pdb.gimp_layer_set_mode(resl, SOFTLIGHT_MODE)
    return resl

  #override method, drawing the forest in the selection (when the method is called, a selection channel for the forest should be already present)
  def generatestep(self):    
    #creating noise base for the trees, this will be used to create a detailed mask for the trees
    self.bgl = self.makenoisel(self.textes["baseln"] + "basicnoise", 16, 16, NORMAL_MODE, True, True)
    self.shapelayer, self.addingchannel = self.overdrawmask(self.bgl, self.textes["baseln"], 30, self.addingchannel, True)
    self.appendmask(self.addingchannel, False)

    #creating the bump needed to make the forest
    pdb.plug_in_hsv_noise(self.img, self.shapelayer, 2, 0, 0, 30)
    self.bumplayer = self.makeunilayer(self.textes["baseln"] + "bump", (127, 127, 127)) #50% gray color
    self.addmaskp(self.bumplayer, self.addingchannel)
    pdb.plug_in_bump_map_tiled(self.img, self.bumplayer, self.shapelayer, 135, 30, 8, 0, 0, 0, 0, True, False, 2) #2 (last) = sinusoidal
    
    pdb.gimp_image_select_item(self.img, 2, self.addingchannel)
    pdb.script_fu_drop_shadow(self.img, self.bumplayer, 2, 2, 15, (0, 0, 0), 75, False)
    self.forestshadow = [i for i in self.getgroupl().layers if i.name == "Drop Shadow"][0]
    self.forestshadow.name = self.textes["baseln"] + "shadow"
    pdb.gimp_selection_none(self.img)
    
    #adding colors
    self.colorlayers.append(self.addforestcol(self.browncol))
    self.colorlayers.append(self.addforestcol(self.greencol))
    self.colorlayers.append(self.addforestcol(self.yellowcol))
    
    pdb.gimp_displays_flush()


#class to drawing the rivers
class RiversBuild(GlobalBuilder):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    mwin = GlobalBuilder.__init__(self, image, None, layermask, channelmask, False, False, *args)
    
    self.riversmask = None
    self.bumpsmap = None
    self.bevels = None
    self.watercol = (49, 64, 119)
    self.defsize = 0.01 * (self.img.width + self.img.height)

    self.namelist = ["rivers", "riversbumps", "riversbevels"]
    
    #new row
    labtxt = "Adding rivers to the map. If you do not want to draw rivers, just press Next.\n"
    labtxt += "Rivers can not be added randomly, you must draw them.\nThe script will instruct you when you have to do it." 
    laba = gtk.Label(labtxt)
    self.vbox.add(laba)
    
    #action area
    self.add_button_quit()
    self.add_button_generate("Draw Rivers")
    self.add_button_nextprev()
    
    return mwin
    
  #override cleaning method
  def cleandrawables(self):
    self.deletedrawables(self.bevels, self.bumpsmap)

  #override loading method
  def loaddrawables(self):
    for ll in self.img.layers:
      if ll.name == self.namelist[0]:
        self.bgl = ll
      elif ll.name == self.namelist[1]:
        self.bumpsmap = ll
      elif ll.name == self.namelist[2]:
        self.bevels = ll
    return self.loaded()
    
  #override method, do rivers step
  def generatestep(self):    
    #creating the color layer and applying masks
    self.bgl = self.makeunilayer("rivers", self.watercol)
    self.addmaskp(self.bgl, self.channelms, False, True)
    maskdiff = self.addmaskp(self.bgl, self.channelms, True)
    
    #saving the difference mask in a layer for bevels
    difflayer = self.makeunilayer("riversdiff")
    pdb.gimp_edit_copy(maskdiff)
    flsel = pdb.gimp_edit_paste(difflayer, False)
    pdb.gimp_floating_sel_anchor(flsel)
    pdb.gimp_item_set_visible(difflayer, False)

    #setting stuffs for the user
    pdb.gimp_image_set_active_layer(self.img, self.bgl)
    oldfgcol = pdb.gimp_context_get_foreground()
    pdb.gimp_context_set_foreground((255, 255, 255)) #set foreground color
    pdb.gimp_context_set_brush_size(self.defsize)

    #dialog to explain the user that is time to draw
    infodial = gtk.Dialog(title="Drawing rivers", parent=self)
    labtxt = "Draw the rivers on the map. Regulate the size of the pencil if needed.\n"
    labtxt += "Use the pencil and do not worry of drawing on the sea.\n"
    labtxt += "Do not change the foreground color (it has to be white as you are actually editing the layer mask).\n"
    labtxt += "Press OK when you have finished to draw the rivers."
    ilabel = gtk.Label(labtxt)
    infodial.vbox.add(ilabel)
    ilabel.show()
    infodial.add_button("OK", gtk.RESPONSE_OK)
    rr = infodial.run()
    
    #steps after the rivers have been drawn
    if rr == gtk.RESPONSE_OK:
      infodial.destroy()
      pdb.gimp_context_set_foreground(oldfgcol)
      
      #saving the edited mask in a layer for bevels
      self.bumpsmap = self.makeunilayer("riversbumps")
      self.riversmask = pdb.gimp_layer_get_mask(self.bgl)
      pdb.gimp_edit_copy(self.riversmask)
      flsel = pdb.gimp_edit_paste(self.bumpsmap, False)
      pdb.gimp_floating_sel_anchor(flsel)

      #merging the layer to have only the rivers for the bump map
      pdb.gimp_item_set_visible(difflayer, True)
      pdb.gimp_layer_set_mode(self.bumpsmap, DIFFERENCE_MODE)
      self.bumpsmap = pdb.gimp_image_merge_down(self.img, self.bumpsmap, 0)
      self.bumpsmap.name = "riversbumps"
      pdb.gimp_invert(self.bumpsmap)
      pdb.gimp_item_set_visible(self.bumpsmap, False)
      
      #making the bevels with a bump map
      self.bevels = self.makeunilayer("riversbevels", (127, 127, 127))
      pdb.plug_in_bump_map_tiled(self.img, self.bevels, self.bumpsmap, 120, 45, 3, 0, 0, 0, 0, True, False, 2) #2 = sinusoidal
      pdb.gimp_layer_set_mode(self.bevels, OVERLAY_MODE)

    pdb.gimp_displays_flush()


#class to add symbols (towns, capital towns, and so on)
class SymbolsBuild(GlobalBuilder):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    mwin = GlobalBuilder.__init__(self, image, None, layermask, channelmask, False, False, *args)

    self.symbols = None

    self.basepath = os.path.dirname(os.path.abspath(__file__)) + "/make_landmap_brushes/"
    self.defsize = 0.025 * (self.img.width + self.img.height)
    self.chsize = self.defsize
    self.bgcol = (223, 223, 83)
    self.brushnames = ["Town", "Capital", "Port", "Wallfort", "Ruin"]
    self.prevbrush = None
    self.prevbrushsize = None

    self.namelist = ["symbols outline", "symbols"]

    #Designing the interface
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxa)
    
    labatxt = "Adding symbols for towns and similars. Click on the button to select the brush with the proper symbol.\n"
    labatxt += "Use the pencil and set the pencil size as appropriate if you wish bigger or smaller symbols.\n"
    labatxt += "You must have a copy of the brushes which come with this plug-in saved in the GIMP brushes directory." 
    laba = gtk.Label(labatxt)
    hbxa.add(laba)
    
    #new row
    hbxb = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hbxb)

    buttown = self.addbuttonimage(self.brushnames[0], self. basepath + "brushtown.png")
    hbxb.add(buttown)
    
    butcap = self.addbuttonimage(self.brushnames[1], self. basepath + "brushcapital.png")
    hbxb.add(butcap)
    
    butport = self.addbuttonimage(self.brushnames[2], self. basepath + "brushport.png")
    hbxb.add(butport)
    
    butfort = self.addbuttonimage(self.brushnames[3], self. basepath + "brushwallfort.png")
    hbxb.add(butfort)
    
    butruin = self.addbuttonimage(self.brushnames[4], self. basepath + "brushruin.png")
    hbxb.add(butruin)

    #new row
    hbxc = gtk.HBox(spacing=10, homogeneous=False)
    self.vbox.add(hbxc)

    labc = gtk.Label("Set brush size")
    hbxc.add(labc)

    brsizadj = gtk.Adjustment(self.defsize, 5, int(0.1*(self.img.width + self.img.height)), 1, 10)    
    scalec = gtk.HScale(brsizadj)
    scalec.set_size_request(120, 45)
    scalec.connect("value-changed", self.on_brsize_changed)
    hbxc.add(scalec)

    spbutc = gtk.SpinButton(brsizadj, 0, 0)
    spbutc.connect("output", self.on_brsize_changed)
    hbxc.add(spbutc)

    #action area
    self.add_button_quit()
    
    butcanc = gtk.Button("Cancel Symbols")
    self.action_area.add(butcanc)
    butcanc.connect("clicked", self.on_cancel_clicked)
    
    butrand = gtk.Button("Add randomly")
    self.action_area.add(butrand)
    butrand.connect("clicked", self.on_random_clicked)
    
    self.add_button_nextprev()
  
    return mwin

  #nested class, controlling random displacement of symbols
  class RandomSymbols(gtk.Dialog):
    #constructor
    def __init__(self, *args):
      swin = gtk.Dialog.__init__(self, *args)
      self.set_border_width(10)
      
      self.nsym = 1
      self.rsymbplace = 0
      
      #new row
      hbxa = gtk.HBox(spacing=10, homogeneous=True)
      self.vbox.add(hbxa)
      
      laba = gtk.Label("How many symbols do you want to add?")
      hbxa.add(laba)
      
      nsymadj = gtk.Adjustment(self.nsym, 1, 10, 1, 10)
      spbuta = gtk.SpinButton(nsymadj, 0, 0)
      spbuta.connect("output", self.on_nsym_changed)
      hbxa.add(spbuta)

      #new row
      vbxb = gtk.VBox(spacing=10, homogeneous=True)
      self.vbox.add(vbxb)

      self.raba = gtk.RadioButton(None, "Adding symbols on land only")
      self.raba.connect("toggled", self.on_radiob_toggled, 0)
      vbxb.add(self.raba)
      self.rabb = gtk.RadioButton(self.raba, "Adding symbols in the full image")
      self.rabb.connect("toggled", self.on_radiob_toggled, 1)
      vbxb.add(self.rabb)
      self.rabc = gtk.RadioButton(self.raba, "Adding symbols in a hand-made selection")
      self.rabc.connect("toggled", self.on_radiob_toggled, 2)
      vbxb.add(self.rabc)
      
      #button area
      self.add_button("Cancel", gtk.RESPONSE_CANCEL)
      self.add_button("OK", gtk.RESPONSE_OK)
      
      self.show_all()
      return swin
      
    #callback method, set the number of symbols to be added
    def on_nsym_changed(self, widget):
      self.nsym = widget.get_value()

    #callback method, set if symbols have to be added on land only
    def on_radiob_toggled(self, widget, vv):
      self.rsymbplace = vv

  #outer class methods
  #method, adding a selecting brush button with image and label in the button area
  def addbuttonimage(self, brname, iconfile):
    butres = gtk.Button()
    vbx = gtk.VBox(spacing=0, homogeneous=True)

    img = gtk.Image()
    img.set_from_file(iconfile)
    vbx.add(img)

    lab = gtk.Label(brname)
    vbx.add(lab)

    butres.add(vbx)
    butres.connect("clicked", self.on_brush_chosen, brname)

    return butres

  #override cleaning method
  def cleandrawables(self):
    self.deletedrawables(self.symbols)
    self.bgl = None
    self.symbols = None

  #override loading method
  def loaddrawables(self):
    for ll in self.img.layers:
      if ll.name == self.namelist[0]:
        self.bgl = ll
      if ll.name == self.namelist[1]:
        self.symbols = ll
    return self.loaded()
        
  #override method to prepare the symbols drawing 
  def setbeforerun(self):
    if self.bgl is None:
      self.bgl = self.makeunilayer("symbols outline")
      pdb.plug_in_colortoalpha(self.img, self.bgl, (255, 255, 255))

    if self.symbols is None:
      self.symbols = self.makeunilayer("symbols")
      pdb.plug_in_colortoalpha(self.img, self.symbols, (255, 255, 255))
    
    pdb.gimp_displays_flush()

  #callback method to set the brush size
  def on_brsize_changed(self, widget):
    self.chsize = widget.get_value()
    pdb.gimp_context_set_brush_size(self.chsize)

  #callback method to select the proper brush
  def on_brush_chosen(self, widget, brushstr):
    pdb.gimp_plugin_set_pdb_error_handler(1)
    if self.prevbrush is None:
      self.prevbrush = pdb.gimp_context_get_brush()
    if self.prevbrushsize is None:
      self.prevbrushsize = pdb.gimp_context_get_brush_size()
    
    try:
      pdb.gimp_context_set_brush('make_landmap brush ' + brushstr)
    except RuntimeError, errtxt:
      #dialog explaining the occurred error
      errdi = gtk.Dialog(title="Error", parent=self)
      elabtxt = "Error message: " + errtxt.message + "\nDid you add the make_landmap brushes to the GIMP brushes folder?"
      elabel = gtk.Label(elabtxt)
      errdi.vbox.add(elabel)
      elabel.show()
      errdi.add_button("Ok", gtk.RESPONSE_OK)
      rr = errdi.run()
      if rr == gtk.RESPONSE_OK:
        errdi.destroy()

    pdb.gimp_context_set_brush_size(self.chsize)
    pdb.gimp_plugin_set_pdb_error_handler(0)

  #callback method, add randomly a given number of symbols.
  def on_random_clicked(self, widget):
    rnds = self.RandomSymbols("Adding symbols randomly", self, gtk.DIALOG_MODAL)
    rr = rnds.run()
    if rr == gtk.RESPONSE_OK:
      i = 0
      tempchannel = None
      while i < int(rnds.nsym):
        xc = random.random() * self.img.width
        yc = random.random() * self.img.height
        if rnds.rsymbplace == 0:
          if self.checkpixelcoord(xc, yc):
            pdb.gimp_paintbrush_default(self.symbols, 2, [xc, yc])
            i = i + 1
        elif rnds.rsymbplace == 1:
          pdb.gimp_paintbrush_default(self.symbols, 2, [xc, yc])
          i = i + 1
        elif rnds.rsymbplace == 2:
          #check if a selection is present or the temporary channel mask has been created
          if not pdb.gimp_selection_is_empty(self.img) or tempchannel is not None:
            if tempchannel is None:
              tempchannel = pdb.gimp_selection_save(self.img)
              tempchannel.name = "temporarymask"
              pdb.gimp_selection_none(self.img)
            if self.checkpixelcoord(xc, yc, tempchannel):
              pdb.gimp_paintbrush_default(self.symbols, 2, [xc, yc])
              i = i + 1
          else:
            infodi = gtk.Dialog(title="Info", parent=self)
            imess = "Select the area where you want to place the symbols with the lazo tool or another selection tool first!\n"
            ilabel = gtk.Label(imess)
            infodi.vbox.add(ilabel)
            ilabel.show()
            infodi.add_button("Ok", gtk.RESPONSE_OK)
            diresp = infodi.run()
            if (diresp == gtk.RESPONSE_OK):
              infodi.destroy()
              break

      if tempchannel is not None:
        pdb.gimp_image_remove_channel(self.img, tempchannel)

      pdb.gimp_displays_flush()
    
    rnds.destroy()

  #callback method, cancel symbols and close step
  def on_cancel_clicked(self, widget):
    self.cleandrawables()
    self.setgenerated(False)
    self.setbeforerun()
    
  #override method to fix symbols, add finishing touches and close.
  def afterclosing(self, who):
    #we cannot know before calling this method the first time if the step has been generated or not as the boolean variable is set here.
    if self.get_brightness_max(self.symbols) != -1: #check the histogram, verify that is not a fully transparent layer.
      if not self.generated:
        pdb.gimp_image_select_item(self.img, 2, self.symbols) #2 = replace selection, this select everything in the layer which is not transparent
        pdb.gimp_selection_grow(self.img, 2)
        pdb.gimp_selection_feather(self.img, 5)
        colfillayer(self.img, self.bgl, self.bgcol)
        pdb.gimp_selection_none(self.img)
        self.setgenerated(True)
        if self.prevbrush is not None:
          pdb.gimp_context_set_brush(self.prevbrush)
        if self.prevbrushsize is not None:
          pdb.gimp_context_set_brush_size(self.prevbrushsize)
    else:
      pdb.gimp_image_remove_layer(self.img, self.bgl)
      pdb.gimp_image_remove_layer(self.img, self.symbols)
      
    pdb.gimp_displays_flush()


#class to add roads
class RoadBuild(GlobalBuilder):
  #constructor
  def __init__(self, image, layermask, channelmask, *args):
    mwin = GlobalBuilder.__init__(self, image, None, layermask, channelmask, False, True, *args)

    self.roadslayers = []
    self.paths = []
    self.roadlinelist = ["Solid", "Long dashed", "Medium dashed", "Short dashed", "Sparse dotted", \
    "Normal dotted", "Dense dotted", "Stipples", "Dash dotted", "Dash dot dotted"]
    self.typelist = range(len(self.roadlinelist))
    self.chtype = 0 #will be reinitialized in GUI costruction
    self.roadcolor = (0, 0, 0)
    self.roadsize = 5

    self.namelist = ["roads", "drawroads"]

    #Designing the interface
    #new row
    hboxa = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hboxa)
    
    labatxt = "Adding roads. You are going to use paths. Click on the top path in the Paths panel to activate the path tool.\n"
    labatxt += "Place paths between cities, place nodes and curves. The roads will be drawn on the paths you are going to place by clicking the 'Draw Roads' button.\n"
    labatxt += "You can repeat this step: just select the new Path that is created each time the roads are drawn and place new paths.\n"
    labatxt += "If you have a svg file with paths that you wish to import to use as roads, import it through the 'Import from SVG file' button.\n"
    labatxt += "Change color, size or type line if you wish and click again the 'Draw Roads' button."
    laba = gtk.Label(labatxt)
    hboxa.add(laba)

    #new row
    hboxb = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hboxb)
    
    labb = gtk.Label("Choose type of line")
    hboxb.add(labb)
    
    boxmodelb = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT)
    
    #filling the model for the combobox
    for i, j in zip(self.roadlinelist, self.typelist):
      irow = boxmodelb.append(None, [i, j])

    self.chtype = self.typelist[1]

    cboxb = gtk.ComboBox(boxmodelb)
    rendtextb = gtk.CellRendererText()
    cboxb.pack_start(rendtextb, True)
    cboxb.add_attribute(rendtextb, "text", 0)
    cboxb.set_entry_text_column(0)
    cboxb.set_active(1)
    cboxb.connect("changed", self.on_line_changed)
    hboxb.add(cboxb)

    #new row
    hboxc = gtk.HBox(spacing=10, homogeneous=True)
    self.vbox.add(hboxc)
    
    labc = gtk.Label("Road colors")
    hboxc.add(labc)

    butcolor = gtk.ColorButton()
    butcolor.set_title("Select road colors")
    hboxc.add(butcolor)
    butcolor.connect("color-set", self.on_butcolor_clicked)

    labcc = gtk.Label("Road size (pixels)")
    hboxc.add(labcc)

    rsizadj = gtk.Adjustment(self.roadsize, 2, 30, 1, 5)
    spbutc = gtk.SpinButton(rsizadj, 0, 0)
    spbutc.connect("output", self.on_rsize_changed)
    hboxc.add(spbutc)
    
    #action area
    self.add_button_quit()

    butcanc = gtk.Button("Cancel Roads")
    self.action_area.add(butcanc)
    butcanc.connect("clicked", self.on_cancel_clicked)

    butimpo = gtk.Button("Import from SVG file")
    self.action_area.add(butimpo)
    butimpo.connect("clicked", self.on_import_clicked)

    self.add_button_generate("Draw Roads")
    self.add_button_nextprev()

    return mwin

  #class holding the interface to delete paths
  class DelPaths(gtk.Dialog):
    #constructor
    def __init__(self, outobject, *args):
      swin = gtk.Dialog.__init__(self, *args)
      self.set_border_width(10)
      self.outobj = outobject
      self.selpath = -1
      self.sellayer = -1

      #new row
      hbxa = gtk.HBox(spacing=10, homogeneous=True)
      self.vbox.add(hbxa)
      
      laba = gtk.Label("Select the name of the path you want to delete.")
      hbxa.add(laba)

      #new row
      hboxb = gtk.HBox(spacing=10, homogeneous=True)
      self.vbox.add(hboxb)
            
      boxmodelb = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_INT, gobject.TYPE_INT)
      pathsnames = ["All"] + [ll.name for ll in self.outobj.paths]
      pathsidx = [-1] + range(len(self.outobj.paths[:-1]))
      rlidx = [-1] + range(len(self.outobj.roadslayers[:-1]))
      
      #filling the model for the combobox
      for i, j, k in zip(pathsnames, pathsidx, rlidx):
        irow = boxmodelb.append(None, [i, j, k])

      cboxb = gtk.ComboBox(boxmodelb)
      rendtextb = gtk.CellRendererText()
      cboxb.pack_start(rendtextb, True)
      cboxb.add_attribute(rendtextb, "text", 0)
      cboxb.set_entry_text_column(0)
      cboxb.set_active(0)
      cboxb.connect("changed", self.on_selroad_changed)
      hboxb.add(cboxb)

      #button area
      self.add_button("Cancel", gtk.RESPONSE_CANCEL)
      self.add_button("OK", gtk.RESPONSE_OK)
      
      self.show_all()
      return swin

    #callback method to select the path to be deleted
    def on_selroad_changed(self, widget):
      refmode = widget.get_model()
      self.selpath = refmode.get_value(widget.get_active_iter(), 1)
      self.sellayer = refmode.get_value(widget.get_active_iter(), 2)

    #method to get the selected path (vector and layer objects)
    def getselected(self):
      return self.selpath, self.sellayer

  #outer class methods
  #overriding method to check if the step has generated some roads
  def loaded(self):
    if len(self.paths) > 0:
      self.setgenerated(True)
      return True
    else:
      return False
  
  #callback method, setting the type line
  def on_line_changed(self, widget):
    refmode = widget.get_model()
    self.chtype = refmode.get_value(widget.get_active_iter(), 1)

  #callback method, setting the road color
  def on_butcolor_clicked(self, widget):
    self.roadcolor = gdkcoltorgb(widget.get_color())

  #callback method, setting the road size
  def on_rsize_changed(self, widget):
    self.roadsize = widget.get_value()
    
  #override method to prepare the road drawing 
  def setbeforerun(self):
    #adding a transparent layer
    self.roadslayers.append(self.makeunilayer("drawroads" + str(len(self.roadslayers))))
    pdb.plug_in_colortoalpha(self.img, self.roadslayers[-1], (255, 255, 255))
    pdb.gimp_layer_set_mode(self.roadslayers[-1], OVERLAY_MODE)

    #adding an empty path
    self.paths.append(pdb.gimp_vectors_new(self.img, "roads" + str(len(self.paths))))
    pdb.gimp_image_insert_vectors(self.img, self.paths[-1], None, 0)
    pdb.gimp_image_set_active_vectors(self.img, self.paths[-1])
    pdb.gimp_displays_flush()
    
  #override cleaning method 
  def cleandrawables(self):
    fullist = self.roadslayers + self.paths
    self.deletedrawables(*fullist)
    del self.roadslayers[:]
    del self.paths[:]

  #override loading method
  def loaddrawables(self):
    for pl in self.img.vectors:
      if self.namelist[0] in pl.name:
        self.paths.append(pl)
    for ll in self.img.layers:
      if self.namelist[1] in ll.name:
        self.roadslayers.append(ll)
    return self.loaded()

  #drawing the roads
  def generatestep(self):
    oldfgcol = pdb.gimp_context_get_foreground()
    pdb.gimp_context_set_foreground((255, 255, 255)) #set foreground color to white

    try:
      pdb.python_fu_stroke_vectors(self.img, self.roadslayers[-1], self.paths[-1], self.roadsize, 0)
    except:
      pdb.gimp_edit_stroke_vectors(self.bgl, self.paths[-1])

    pdb.gimp_context_set_foreground(self.roadcolor) #set foreground color to black
    try:
      pdb.python_fu_stroke_vectors(self.img, self.roadslayers[-1], self.paths[-1], self.roadsize/2, self.chtype)
    except:
      pdb.gimp_edit_stroke_vectors(self.bgl, self.paths[-1])
    
    pdb.gimp_context_set_foreground(oldfgcol)

  #callback method to cancel all roads
  def on_cancel_clicked(self, widget):
    pathselecter = self.DelPaths(self, "Removing roads", self, gtk.DIALOG_MODAL)
    rr = pathselecter.run()

    if rr == gtk.RESPONSE_OK:
      pathtod, layertod = pathselecter.getselected()

      if pathtod == -1 or layertod == -1:
        self.cleandrawables()
        self.setgenerated(False)
        self.setbeforerun()
      else:
        pdb.gimp_image_remove_vectors(self.img, self.paths[pathtod])
        pdb.gimp_image_remove_layer(self.img, self.roadslayers[layertod])
        del self.paths[pathtod]
        del self.roadslayers[layertod]
        if len(self.roadslayers) == 0:
          self.setgenerated(False)

      pdb.gimp_displays_flush()
    pathselecter.destroy()

  #callback method to draw roads
  def on_import_clicked(self, widget):
    filechooser = gtk.FileChooserDialog ("Choose SVG file", self, gtk.FILE_CHOOSER_ACTION_OPEN, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK), None)
    swf_filter = gtk.FileFilter()
    swf_filter.set_name("SVG (*.svg)")
    swf_filter.add_pattern("*.[Ss][Vv][Gg]")
    filechooser.add_filter(swf_filter)
    rr = filechooser.run()

    #importing and substituting the new vector drawable to the last element in paths
    if rr == gtk.RESPONSE_OK:
      fn = filechooser.get_filename()
      pname = self.paths[-1].name
      pdb.gimp_image_remove_vectors(self.img, self.paths[-1])
      del self.paths[-1]
      pdb.gimp_vectors_import_from_file(self.img, fn, True, True) #it adds the new vectors at position 0 in image.vectors list
      self.img.vectors[0].name = pname
      self.paths.append(self.img.vectors[0])

    filechooser.destroy()

  #override method to delete the last vectors drawable
  def afterclosing(self, who):
    pdb.gimp_image_remove_vectors(self.img, self.paths[-1])
    pdb.gimp_image_remove_layer(self.img, self.roadslayers[-1])
    del self.paths[-1]
    del self.roadslayers[-1]
    

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
    self.set_title("Make land map")
    vbx = gtk.VBox(spacing=10, homogeneous=False)
    self.add(vbx)
    
    #new row
    hbxa = gtk.HBox(spacing=10, homogeneous=True)
    vbx.add(hbxa)

    mainmess = "This plugins allows you to draw regional map. Start from an image with a single layer with white background.\n\
Press the 'Generate new map' button to start drawing your map. Popup dialogs will lead you in the process step by step.\n\
To continue working on a saved map, simply load the map in gimp (should be saved as a.xcf file), then start the plug-in.\n\
Press the 'Work on current map' button. The plug-in will start at the last generated step drawn in the map."
    laba = gtk.Label(mainmess)
    hbxa.add(laba)

    #new row
    hbxb = gtk.HBox(spacing=10, homogeneous=True)
    vbx.add(hbxb)
    
    butgenmap = gtk.Button("Generate new map")
    hbxb.add(butgenmap)
    butgenmap.connect("clicked", self.on_butgenmap_clicked)

    butusemap = gtk.Button("Work on current map")
    hbxb.add(butusemap)
    butusemap.connect("clicked", self.on_butusemap_clicked)

    self.show_all()
    return mwin

  #method to create all the builders
  def instantiatebuilders(self, layermask, channelmask, iswater, loading):
    builderlist = []
    self.landdet = BaseDetails(self.img, layermask, channelmask, "Building land details", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args

    if iswater:
      self.water = WaterBuild(self.img, layermask, channelmask, "Building water mass", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
      self.landdet.refbg = self.water
      builderlist.append(self.water)
      firstbuilder = self.water
    else:
      self.landdet.refbg = self.drawab
      firstbuilder = self.landdet

    builderlist.append(self.landdet)
    self.dirtd = DirtDetails(self.img, layermask, channelmask, "Building dirt", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    builderlist.append(self.dirtd)
    self.mount = MountainsBuild(self.img, layermask, channelmask, "Building mountains", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    builderlist.append(self.mount)
    self.forest = ForestBuild(self.img, layermask, channelmask, "Building forests", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    builderlist.append(self.forest)
    self.rivers = RiversBuild(self.img, layermask, channelmask, "Building rivers", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    builderlist.append(self.rivers)
    self.symbols = SymbolsBuild(self.img, layermask, channelmask, "Adding symbols", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    builderlist.append(self.symbols)
    self.roads = RoadBuild(self.img, layermask, channelmask, "Adding roads", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    builderlist.append(self.roads)
        
    #setting stuffs
    if iswater > 0:
      self.water.setreferences(None, self.landdet)
      self.landdet.setreferences(self.water, self.dirtd)
    else:
      self.landdet.setreferences(None, self.dirtd)
    self.dirtd.setreferences(self.landdet, self.mount)
    self.mount.setreferences(self.dirtd, self.forest)
    self.forest.setreferences(self.mount, self.rivers)
    self.rivers.setreferences(self.forest, self.symbols)
    self.symbols.setreferences(self.rivers, self.roads)
    self.roads.setreferences(self.symbols, None)

    #loading already present layers and setting the first drawable to launch
    if loading:
      foundlast = False
      for bb in builderlist[::-1]: #working on a reversed list
        if bb.loaddrawables() and not foundlast:
          foundlast = True
          firstbuilder = bb

    return firstbuilder

  #method calling the object builder, listening to the response, and recursively calling itself
  def buildingmap(self, builder):
    builder.show_all()
    builder.setbeforerun()
    builder.run()
    proxb = builder.chosen
    if proxb is not None:
      self.buildingmap(proxb)

  #callback method to generate the map randomly
  def on_butgenmap_clicked(self, widget):
    pdb.gimp_context_set_foreground((0, 0, 0)) #set foreground color to black
    pdb.gimp_context_set_background((255, 255, 255)) #set background to white
    pdb.gimp_selection_none(self.img) #unselect if there is an active selection
    
    landtextes = {"baseln" : "land", \
    "labelext" : "land", \
    "namelist" : ["no water", "archipelago/lakes", "simple coastline", "island", "big lake", "customized"], \
    "toplab" : "In the final result: white represent land and black represent water.", \
    "topnestedlab" : "Position of the landmass in the image."}

    #building the land profile
    self.land = MaskProfile(landtextes, self.img, self.drawab, None, None, "Building land mass", self, gtk.DIALOG_MODAL) #title = "building...", parent = self, flag = gtk.DIALOG_MODAL, they as passed as *args
    self.land.run()
    
    layermask = self.land.maskl
    channelmask = self.land.channelms
    if channelmask is not None:
      channelmask.name = landtextes["baseln"] + "mask"

    dowater = True
    if self.land.chtype == 0:
      dowater = False

    fb = self.instantiatebuilders(layermask, channelmask, dowater, False)
    self.buildingmap(fb)
  
  #callback method to use current image as map
  def on_butusemap_clicked(self, widget):
    lilaym = [ll for ll in self.img.layers if ll.name == "landlayer"]
    lichm = [ch for ch in self.img.channels if ch.name == "landmask"]

    layermask = None
    if len(lilaym) == 1:
      layermask = lilaym[0]

    channelmask = None
    dowater = False
    if len(lichm) == 1:
      channelmask = lichm[0]
      dowater = True

    fb = self.instantiatebuilders(layermask, channelmask, dowater, True)
    
    self.buildingmap(fb)


#The function to be registered in GIMP
def python_make_landmap(img, tdraw):
  #query the procedure database
  numfelimg, _ = pdb.gimp_procedural_db_query("plug-in-fimg-noise", ".*", ".*", ".*", ".*", ".*", ".*")
  if numfelimg == 0:
    messtxt = "Warning: you need to install the felimage plugin to use all the features of this plugin properly.\n"
    messtxt += "Without the felimage plugin, the mountains will be of poor quality."  
    pdb.gimp_message(messtxt)

  #query the procedure database
  numstrokevect, _ = pdb.gimp_procedural_db_query("python-fu-stroke-vectors", ".*", ".*", ".*", ".*", ".*", ".*")
  if numstrokevect == 0:
    messtxt = "Warning: you need to install the stroke_vector_options.py plugin to use all the features of this plugin.\n"
    messtxt += "Without the stroke_vector_options.py plugin, roads will be always solid lines and brush sized, whatever options you select."
    pdb.gimp_message(messtxt)
    
  mapp = MainApp(img, tdraw)
  gtk.main()


#The command to register the function
register(
  "python-fu_make-landmap",
  "python-fu_make-landmap",
  "Draw a regional map. Popup dialogs will guide the user in the process.",
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
