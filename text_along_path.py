#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  text_along_path.py
#  
#  Copyright 2018 Valentino Esposito <valentinoe85@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
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

import sys
import os
import math
from gimpfu import *

class CompBezierCurve:
  '''Class holding the control points of a composite Bézier curve.
  Two CBCPoint objects are needed to draw a cubic Bézier curve between them. This curve is part of a composite Bézier curve,
  ensuring continuity of the whole curve (no guarantee that first derivative will be equal at the joining point).
  Methods of this class allow to get the points and length of any Bézier curve of the composite Bézier curve.
  '''
  
  class Point:
    '''Class holding x and y coordinates of a point. Provide some methods to quickly get and set the values'''
    #constructor
    def __init__(self, x=None, y=None):
      if x is None and y is None:
        self.x = 0
        self.y = 0
      if y is not None:
        self.x = x
        self.y = y
      else:
        if isinstance(x, (list, tuple)):
          self.x = x[0]
          self.y = x[1]
        elif isinstance(x, (dict)):
          self.x = x['x']
          self.y = x['y']

      try:
        self.x
        self.y
      except AttributeError, e:
        print "Error in initializing Point:", e

    def __getitem__(self, key):
      '''overloading getitem operator'''
      if key in [0, 'x']:
        return self.x
      elif key in [1, 'y']:
        return self.y
      else:
        raise ValueError("Error in getitem. key parameter must be 0, 'x', 1, 'y'")

    def __setitem__(self, key, item):
      '''overloading setitem operator'''
      if key in [0, 'x']:
        self.x = item
      elif key in [1, 'y']:
        self.y = item
      else:
        raise ValueError("Error in setitem. key parameter must be 0, 'x', 1, 'y'")
        
    def __repr__(self):
      return '(x: ' + str(self.x) + ', y:' + str(self.y) + ')'

    def __str__(self):
      return str(self.x) + ', ' + str(self.y) + ';'

    def __add__(self, other):
      '''overloading __add__ (+) operator'''
      return CompBezierCurve.Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
      '''overloading __sub__ (-) operator'''
      return CompBezierCurve.Point(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
      '''overloading __mul__ (*) operator'''
      if isinstance(other, CompBezierCurve.Point):
        return (self.x * other.x) + (self.y * other.y)
      else:
        return CompBezierCurve.Point(self.x * other, self.y * other)

    def __rmul__(self, other):
      '''overloading __rmul__ (*) operator'''
      return self.__mul__(other)

    def distp(self, ap):
      '''Distance from Point to another Point ap'''
      return math.sqrt(math.pow((self.x - ap.x), 2) + math.pow((self.y - ap.y), 2))

    def pointatdist(self, ap, d):
      '''Get the coordinate of a point ad distance d from this point in direction of another point ap.
      d is in units of the point - ap distance (e.g. t = 1 is the point ap).
      '''
      res = CompBezierCurve.Point()
      for l in ['x', 'y']:
        res[l] = self[l] + d*(ap[l] - self[l])
      return res


  class CBCPoint:
    '''Class holding three control points of a 2D composite Bézier curve. They are three points in the x, y plane.
    First and third points control the direction of the curve, second point belongs to the curve.
    Costruction of the composite Bézier curve is delegated to the main class.
    '''
    #constructor
    def __init__(self, *points):
      errmess = "argument must be: one list/tuple of length 6, three lists/tuples/ of lenght 2, "
      errmess += "3 CompBezierCurve.Point objects, or 6 numeric arguments."
      if len(points) == 1 and isinstance(points[0], (list, tuple)):
        if len(points[0]) == 6:
          pp = points[0]
          self.cda = CompBezierCurve.Point(pp[0], pp[1]) #control direction point A
          self.cmp = CompBezierCurve.Point(pp[2], pp[3]) #main point
          self.cdb = CompBezierCurve.Point(pp[4], pp[5]) #control direction point B
        else:
          raise RuntimeError(errmess)
      elif len(points) == 3 and all([isinstance(i, (list, tuple, CompBezierCurve.Point)) for i in points]):
        if all([isinstance(i, CompBezierCurve.Point) for i in points]):
          self.cda = points[0]  #control direction point A
          self.cmp = points[1] #main point
          self.cdb = points[2] #control direction point B
        elif all([len(i) == 2 for i in points]):
          self.cda = CompBezierCurve.Point(points[0]) #control direction point A
          self.cmp = CompBezierCurve.Point(points[1]) #main point
          self.cdb = CompBezierCurve.Point(points[2]) #control direction point B
        else:
          raise RuntimeError(errmess)
      elif len(points) == 6 and all([isinstance(i, (int, long, float)) for i in points]):
        self.cda = CompBezierCurve.Point(points[0], points[1]) #control direction point A
        self.cmp = CompBezierCurve.Point(points[2], points[3]) #main point
        self.cdb = CompBezierCurve.Point(points[4], points[5]) #control direction point B
      else:
        raise RuntimeError(errmess)

    def __repr__(self):
      return str(self.cda) + ' ' + str(self.cmp) + ' ' + str(self.cdb)

    def __str__(self):
      return str(self.cda) + ' ' + str(self.cmp) + ' ' + str(self.cdb)

    def getctrlp(self, param):
      '''method to get one control point. 0 for the first control point, 1 for the main point, 2 for the second control point
      Control points are returned as dictionaries with x and y coordinates
      '''
      if param == 0:
        return self.cda
      elif param == 1:
        return self.cmp
      elif param == 2:
        return self.cdb
      else:
        raise ValueError("Error, param argument in getctrlp(self, param) method must be 0, 1 or 2")

    def getpts(self):
      '''return a list with the three points'''
      return [self.cda, self.cmp, self.cdb]

    def getxy(self, w):
      '''return a list with the x or y components of the points. w must be: 0, 1, x, y'''
      return [self.cda[w], self.cmp[w], self.cdb[w]]

    def getxyseq(self):
      ll = [(i, j) for i, j in zip(self.getxy('x'), self.getxy('y'))]
      return [c for e in ll for c in e] #flattening the list
      
    def shift(self, x, y):
      '''Shift the path of (x, y)''' 
      temx = [e + x for e in self.getxy('x')]
      temy = [e + y for e in self.getxy('y')]
      return CompBezierCurve.CBCPoint(*[(i, j) for i, j in zip(temx, temy)])

    def scale(self, rx, ry=None):
      '''Scale the path of a ratio rx and ry, each dimension can be scaled independently'''
      if ry is None:
        ry = rx
      temx = [e * rx for e in self.getxy('x')]
      temy = [e * ry for e in self.getxy('y')]
      return CompBezierCurve.CBCPoint(*[(i, j) for i, j in zip(temx, temy)])

  #main class methods
  #constructor
  def __init__(self, *bzp):
    errmess = "Input should be one or more CBCControlPoint objects or a list/tuple whose elements are numeric and its length is multiple of 6"
    if all([isinstance(i, self.CBCPoint) for i in bzp]):
      self.cbc = bzp
    elif len(bzp) % 3 == 0 and all([isinstance(i, self.Point) for i in bzp]):
      np = len(bzp) / 3
      self.cbc = []
      for i in range(np):
        self.cbc.append(self.CBCPoint(*bzp[3*i:3*(i+1)]))
    elif len(bzp) % 6 == 0 and all([isinstance(i, (int, long, float)) for i in bzp]):
      np = len(bzp) / 6
      self.cbc = []
      for i in range(np):
        self.cbc.append(self.CBCPoint(bzp[6*i:6*(i+1)]))
    else:
      raise RuntimeError(errmess)
    self.closed = False

  def __repr__(self):
    restr = "{ "
    for i in range(len(self.cbc)):
      restr += '[ ' + str(self.cbc[i]) + ' ] '
    restr += "}"
    return restr

  def __str__(self):
    restr = "{ "
    for i in range(len(self.cbc)):
      restr += '[ ' + str(self.cbc[i]) + ' ] '
    restr += "}"
    return restr

  def __getitem__(self, key):
    '''overloading getitem operator'''
    return self.cbc[key]

  def __setitem__(self, key, item):
    '''overloading setitem operator'''
    if isinstance(item, self.CBCPoint):
      self.cbc[key] = item
    else:
      raise TypeError("Error! You must assign a CBCControlPoint object.")

  def __delitem__(self, key):
    '''overloading delitem operator'''
    del self.cbc[key]

  def lenseq(self):
    '''return the length of the sequence obtained with getfullseq() method'''
    return len(self.cbc)*6

  def numbezc(self):
    '''return how many Bézier curves there are in the composite Bézier curve'''
    return len(self.cbc)-1

  def getfullseq(self):
    '''return a single list with x0, y0, x1, y1, etc. containing all the points'''
    tmp = [e.getxyseq() for e in self.cbc]
    return [c for e in tmp for c in e] #flattening the list

  def beziercoeff(self, pca, pcb):
    '''Calculate che coefficients of the cubic Bézier curve between pca and pcb, with pca and pcb being
    the two CBCControlPoint objects representing the points at the beginning and ending of the curve.
    '''
    pzero = pca.getctrlp(1)
    pone = pca.getctrlp(2)
    ptwo = pcb.getctrlp(0)
    pthree = pcb.getctrlp(1)

    a = self.Point()
    b = self.Point()
    c = self.Point()

    for l in ['x', 'y']:
      c[l] = 3.0 * (pone[l] - pzero[l])
      b[l] = 3.0 * (ptwo[l] - pone[l]) - c[l]
      a[l] = pthree[l] - pzero[l] - c[l] - b[l]

    return a, b, c, pzero

  def getbezc(self, i, j=None):
    '''Get the CBCPoint objects delimiting from i-th to j-th Bézier curves of the composite Bézier curve.
    If i = j, the CBCPoint objects of the i-th curve only are given.
    '''
    if j is None:
      if i > self.numbezc():
        raise ValueError("i parameter is too high. In this spline there are only " + str(self.numbezc()) + " Bézier curves, i is " + str(i))
      elif i < 1:
        raise ValueError("i parameter is too low. Minimum allowed is 1: i is " + str(i))
      j = i
    else:
      if any([x > self.numbezc() for x in [i, j]]):
        raise ValueError("i or j parameter is too high. In this spline there are only " + str(self.numbezc()) + " Bézier curves: i, j are " + str(i) + " and " + str(j))
      elif any([x < 1 for x in [i, j]]):
        raise ValueError("i or j parameter is too low. Minimum allowed is 1: i, j are " + str(i) + " and " + str(j))
      elif i > j:
        raise ValueError("Must be i <= j")
      
    #retrieving control points of the i-th Bézier curves
    cps = self[i-1:j+1]

    return cps

  def getpat(self, i, t):
    '''Get the coordinate of the point at distance t (0 <= t <= 1) on the i--th Bézier curve
    in the composite Bézier curve. i starts from 1'''
    if t < 0.0 or t > 1.0:
      raise ValueError("t parameter must be between 0 and 1")
    cps = self.getbezc(i)
    
    #calculate coordinates
    ca, cb, cc, cd = self.beziercoeff(cps[0], cps[1])
    res = self.Point()
    for l in ['x', 'y']:
      res[l] = (ca[l] * math.pow(t, 3)) + (cb[l] * math.pow(t, 2)) + (cc[l] * t) + cd[l];

    return res

  def splitbezier(self, t, i, j=None):
    '''split from i-th to j-th Bézier curves of the composite Bézier curve each into two Bézier curves.
    Each curve is splitted at point t (0 <= t <= 1) using de Casteljau's algorithm.
    '''
    cps = self.getbezc(i, j)
    if t in [0.0, 1.0]:
      return CompBezierCurve(*cps)
    else:
      if j is None:
        j = i
      splitpoints = [self.getpat(x, t) for x in range(i, j+1)]
      splitcpl = [cps[0].getctrlp(0)]
      for sp, k in zip(splitpoints, range(len(splitpoints))):
        pzero = cps[k].getctrlp(1)
        pone = cps[k].getctrlp(2)
        ptwo = cps[k+1].getctrlp(0)
        pthree = cps[k+1].getctrlp(1)

        #calculating intermediate points (de Casteljau's algorithm)
        ponefh = pzero.pointatdist(pone, t)
        pmed = pone.pointatdist(ptwo, t)
        ptwosh = ptwo.pointatdist(pthree, t)
        ptwofh = ponefh.pointatdist(pmed, t)
        ponesh = pmed.pointatdist(ptwosh, t)

        #building the new composite Bézier curve
        splitcpl.extend([pzero, ponefh, ptwofh, sp, ponesh, ptwosh])
      splitcpl.extend([cps[-1].getctrlp(1), cps[-1].getctrlp(2)])

      return CompBezierCurve(*splitcpl)
    
  def _lencurveappr(self, i):
    '''Calculate the approximated length of the i-th Bézier curve belonging to the composite Bézier curve.
    i starts from 1. The approximated method consists in calculating the average between the segment
    joining the ending points of the curve and the perimeter given by the three control points.
    '''
    cps = self.getbezc(i)
    pzero = cps[0].getctrlp(1)
    pone = cps[0].getctrlp(2)
    ptwo = cps[1].getctrlp(0)
    pthree = cps[1].getctrlp(1)

    #calculating the approximated length
    chord = pzero.distp(pthree)
    perim = pzero.distp(pone) + pone.distp(ptwo) + ptwo.distp(pthree)
    return (perim + chord) / 2.0

  def lencurve(self, i, t=1.0, precision=1, maxiter=10):
    '''Calculate the approximated length of the i-th Bézier curve belonging to the composite Bézier curve
    with a recursive numerical method up to precision. i starts from 1. Length is calculated from the
    starting point up to t (0 <= t <= 1). The approximated method consists in splitting recursively the original
    curve and using _lencurveappr method on all the splitted curves. maxiter is the number ofmax iteration
    '''
    ccbc = self.splitbezier(t, i)

    ollsum = None
    cc = 0
    while cc < maxiter:
      lc = [ccbc._lencurveappr(k) for k in range(1, ccbc.numbezc()+1)]
      ll = sum(lc)
      if ollsum is not None:
        err = abs(ll - ollsum)
        if abs(err) <= precision:
          break
      ollsum = ll
      ccbc = ccbc.splitbezier(0.5, 1, ccbc.numbezc())
      cc = cc+1

    return ll, err, cc

  def lenfullcurve(self, precision=1, maxiter=10):
    '''Calculate the approximated length of the composite Bézier curve using lencurve method'''
    allenc = [self.lencurve(i, 1.0, precision, maxiter)[0] for i in range(1, self.numbezc()+1)]
    integrlenc = [sum(allenc[:i+1]) for i in range(len(allenc))]
    return integrlenc[-1]
    
  def getpointcbc(self, d, delta=5):
    '''It calculates the coordinate of the point at distance d from the beginning of the composite Bézier curve
    and the slope of the tangent at the point. Distance d and delta are measured on the composite Bézier curve
    in the coordinate units. delta is the step used to calculate the slope (should be greater than the precision
    used in lencurve method to have a reliable estimate of the slope. 
    '''
    allenc = [self.lencurve(i)[0] for i in range(1, self.numbezc()+1)]
    integrlenc = [sum(allenc[:i+1]) for i in range(len(allenc))]
    if d > integrlenc[-1] or d < 0:
      raise ValueError("length outside range: must be greater than 0 or lesser than the total length of the composite Bézier curve")
    else:        
      shiftlenc = [0] + integrlenc[:-1]
      refcurve = [(i+1, l, sil) for i, l, il, sil in zip(range(len(integrlenc)), allenc, integrlenc, shiftlenc) if d <= il and d >= sil][0]
      tt = (d - refcurve[2])/refcurve[1]
      ptcoor = self.getpat(refcurve[0], tt)

      #the derivative
      dt = (1.0 * delta) / refcurve[1]
      try:
        dpp = self.getpat(refcurve[0], tt+dt) - ptcoor
        slp = dpp['y'] / dpp['x']
      except ValueError:
        slp = None

      try:
        dpm = self.getpat(refcurve[0], tt-dt) - ptcoor
        slm = dpm['y'] / dpm['x']
      except ValueError:
        slm = None

      if slp is None:
        slope = slm
      elif slm is None:
        slope = slp
      else:
        slope = (slp + slm) / 2.0
    return ptcoor, slope
    
  def shift(self, x, y):
    '''Shift the full curve by (+x, +y)'''
    return CompBezierCurve(*[e.shift(x, y) for e in self.cbc])

  def scale(self, rx, ry=None):
    '''Scale the path by a ratio rx and ry, each dimension can be scaled independently'''
    if ry is None:
      ry = rx
    return CompBezierCurve(*[e.scale(rx, ry) for e in self.cbc])

    
#A test method using gimp to show curves
def python_bezier_test(img, tdraw, testpath):
  _, tids = pdb.gimp_vectors_get_strokes(testpath)
  _, _, tcps, _ = pdb.gimp_vectors_stroke_get_points(testpath, tids[0])
  bzlp = CompBezierCurve(*tcps)

  for i in [0.0, 0.2, 0.5, 0.8, 1.0]:
    print "point at", i, "in curve 1:", bzlp.getpat(1, i)

  for i in range(1, bzlp.numbezc()+1):
    print "approximate length of curve", str(i) + ":" , bzlp._lencurveappr(i)

  for i in range(1, bzlp.numbezc()+1):
    print "numerically calculated length of curve", str(i) + ":", bzlp.lencurve(i)

  ll = bzlp.lenfullcurve()
  palc, m = bzlp.getpointcbc(ll/2.0)
  print "along the curve:", palc, m

  arbidi = 10
  dirp = CompBezierCurve.Point(palc['x'] + arbidi, palc['y'] + m*arbidi)
  finp = palc.pointatdist(dirp, 6)
  print "on the tangent", finp

  sys.stdout.flush()


#The function to be registered in GIMP
def python_text_along_path(img, tdraw, text, leadpath):
  _, leads_ids = pdb.gimp_vectors_get_strokes(leadpath)
  _, _, leadcps, _ = pdb.gimp_vectors_stroke_get_points(leadpath, leads_ids[0])
  bzclead = CompBezierCurve(*leadcps)

  text_layer = pdb.gimp_text_fontname(img, tdraw, img.width/3, img.height/3, text, 0, False, 60, 0, 'sans-serif')
  textvec = pdb.gimp_vectors_new_from_text_layer(img, text_layer)
  pdb.gimp_image_insert_vectors(img, textvec, None, 0)
  
  _, stroke_ids = pdb.gimp_vectors_get_strokes(textvec)
  bzctext = []
  for sid in stroke_ids:
    _, _, controlpoints, isclosed = pdb.gimp_vectors_stroke_get_points(textvec, sid)
    bzctext.append(CompBezierCurve(*controlpoints))
    bzctext[-1].closed = isclosed

  #recovering coordinates
  allx = []
  ally = []
  for cc in bzctext:
    allx.extend([e.getxy('x')[1] for e in cc.cbc])
    ally.extend([e.getxy('y')[1] for e in cc.cbc])

  #scaling the text to the length of the leading path if the leading path is shorted
  xlen = max(allx) - min(allx)
  bzcleadlen = bzclead.lenfullcurve()
  scalefac = (bzcleadlen / xlen) if (bzcleadlen / xlen) < 1.0 else 1.0 
  scaledbzctext = [i.scale(scalefac) for i in bzctext]

  #shifting the text to the position of the leading path
  vertex = CompBezierCurve.Point(min(allx)*scalefac, max(ally)*scalefac)
  shiftpoint = bzclead[0].getctrlp(1) - vertex
  shiftedbzctext = [i.shift(shiftpoint['x'], shiftpoint['y']) for i in scaledbzctext]

  #recovering coordinates of shifted and scaled text
  ssallx = []
  ssally = []
  for cc in shiftedbzctext:
    ssallx.extend([e.getxy('x')[1] for e in cc.cbc])
    ssally.extend([e.getxy('y')[1] for e in cc.cbc])
  shvertex = CompBezierCurve.Point(min(ssallx), max(ssally))

  #bending the text along the leading path.
  #@@@ try keeping the curves separated, and remembering if they are closed or not
  arbidi = 10
  lowering = 0.98
  bendedbzctext = []
  for cbc in shiftedbzctext:
    bendedpoints = []
    for cbcpp in cbc:
      xdis = cbcpp.getctrlp(1)['x'] - shvertex['x']
      plc, m = bzclead.getpointcbc(lowering*xdis)

      dirp = CompBezierCurve.Point(plc['x'] + arbidi, plc['y'] + m*arbidi)
      ydis = shvertex['y'] - cbcpp.getctrlp(1)['y']
      finp = plc.pointatdist(dirp, (lowering*ydis)/arbidi)
      shiftvec = finp - cbcpp.getctrlp(1)
      bendedpoints.append(cbcpp.shift(shiftvec['x'], shiftvec['y']))

    bendedbzctext.append(CompBezierCurve(*bendedpoints))
    bendedbzctext[-1].closed = cbc.closed

  #showing the text as a new path
  res = pdb.gimp_vectors_new(img, text+'2')
  pdb.gimp_image_insert_vectors(img, res, None, 0)
  for el in bendedbzctext:
    pdb.gimp_vectors_stroke_new_from_points(res, 0, el.lenseq(), el.getfullseq(), el.closed)

  return res


#The command to register the function
register(
  "python-fu-text-along-path",
  "python-fu-text-along-path",
  "Bend a text following the lead of a path",
  "Valentino Esposito",
  "Valentino Esposito",
  "2018",
  "<Image>/Tools/Text Along Path",
  "RGB*, GRAY*, INDEXED*",
  [
    (PF_STRING, "text", "The text to be bent", None),
    (PF_VECTORS, "leadpath", "The path which lead the bending", None),
  ],
  [
    (PF_VECTORS, "bendtext", "The path which represent the bent text"),
  ],
  python_text_along_path
  )

#The command to register the function
register(
  "python-fu-bezier-test",
  "python-fu-bezier-test",
  "TEST: bezier class",
  "Valentino Esposito",
  "Valentino Esposito",
  "2018",
  "<Image>/Tools/BezierTest",
  "RGB*, GRAY*, INDEXED*",
  [
    (PF_VECTORS, "testpath", "The test path", None),
  ],
  [ ],
  python_bezier_test
  )

#The main function to activate the script
main()
