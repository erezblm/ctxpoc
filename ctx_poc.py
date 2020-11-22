import yaml
import midi
from recordtype import recordtype
from copy import deepcopy
import re

tickFactor = 2.0

def getPatterns():
    patterns = {}
    patterns["major"] = [0,4,7]
    patterns["major_upper"] = list(map(lambda n: (n+7)%12, patterns["major"]))
    patterns["major_lower"] = list(map(lambda n: (n-7)%12, patterns["major"]))

    patterns["minor"] = [0,5,8]
    patterns["minor_upper"] = list(map(lambda n: (n-7)%12, patterns["minor"]))
    patterns["minor_lower"] = list(map(lambda n: (n+7)%12, patterns["minor"]))

    patterns["para_major"] = list(map(lambda n: (n-4)%12, patterns["major"]))
    patterns["para_major_upper"] = list(map(lambda n: (n-4)%12, patterns["major_upper"]))
    patterns["para_major_lower"] = list(map(lambda n: (n-4)%12, patterns["major_lower"]))

    patterns["para_minor"] = list(map(lambda n: (n+4)%12, patterns["minor"]))
    patterns["para_minor_upper"] = list(map(lambda n: (n+4)%12, patterns["minor_upper"]))
    patterns["para_minor_lower"] = list(map(lambda n: (n+4)%12, patterns["minor_lower"]))
    return patterns 

patterns = getPatterns()

notes = {'A':0, 'B':2, 'C':3,'D':5,'E':7,'F':8,'G':10}

class Pitch:
    def __init__(self):
        self.zone = None
        self.root = None
        self.pattern = None


Pitch = recordtype('Pitch', ['zone','root','pattern'])
Context = recordtype('Context', ['length', 'time', 'pitch'])


def merge(source, destination):
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = destination.setdefault(key, {})
            merge(value, node)
        else:
            destination[key] = value

    return destination

def createNoteMap(pattern,root):
    note_map = []
  
    shifted_harmonic_pattern = list(map(lambda n: n + root%12, pattern))
    shifted_harmonic_pattern.sort()
    for oct in range(128//12):
        note_map.extend(map(lambda n: n + oct*12, shifted_harmonic_pattern))
    return note_map

def ctx_calculate_note_map_index(note_map, zone):
    first_after_zone = next((i for i,x in enumerate(note_map) if x >= zone), None)
    zero_point = 0
    if first_after_zone == None:
        zero_point = note_map.length - 1
    elif first_after_zone == 0:
        zero_point = 0
    else:
        after_zone_distance = note_map[first_after_zone] - zone
        before_zone_distance = zone - note_map[first_after_zone-1]
        zero_point = first_after_zone if (after_zone_distance <= before_zone_distance) else first_after_zone-1
    
    return zero_point

def calculatePitch(root,zone,pattern,offset):
    notemap = createNoteMap(patterns[pattern],root)
    noteMapIndex = ctx_calculate_note_map_index(notemap, zone) 
    return notemap[noteMapIndex + offset]


midievents = []
lastDivisionEnd = 1.0
timeFactor = None

def allDictToArray(node, count):
    if isinstance(node,list) and len(node) == count:
        return node
    elif isinstance(node,dict):
        res = [{} for sub in range(count)]
        for k,v in node.items():
            for i,v in enumerate(allDictToArray(v,count)):
                res[i][k] = v
        return res
    else:
        raise('array must contain divs count')




def calculateDivsNode(divsNode):
    if 'count' not in divsNode:
        raise 'not found count for divs'
    mergedDivs = [{} for sub in range(divsNode['count'])]
    if 'all' in divsNode:
        mergedDivs = allDictToArray(divsNode['all'],len(mergedDivs))
    for i,div in enumerate(mergedDivs):
        if 'each' in divsNode:
            dest = deepcopy(divsNode['each'])
            mergedDivs[i] = merge(mergedDivs[i], dest)
        if i in divsNode:
            mergedDivs[i] = merge(divsNode[i],mergedDivs[i])
    return mergedDivs

def parseZone(zoneValue):
    if isinstance(zoneValue,int):
        return zoneValue
    elif isinstance(zoneValue,str):
        pattern = f"([{''.join(notes.keys())}])([#b]?)(-?\\d+)"
        match = re.match(pattern,zoneValue)
        if match:
            note = notes[match.group(1)]
            if match.group(2) == '#':
                note = (note + 1) % 12
            elif match.group(2) == 'b':
                note = (note+12 - 1) % 12
            return note + 24 + int(match.group(3))*12
    raise('invalid root value')

def parseRoot(rootValue):
    if isinstance(rootValue,int):
        return rootValue
    elif isinstance(rootValue,str):
        pattern = f"([{''.join(notes.keys())}])([#b]?)"
        match = re.match(pattern,rootValue)
        if match:
            note = notes[match.group(1)]
            if match.group(2) == '#':
                note = (note + 1) % 12
            elif match.group(2) == 'b':
                note = (note+12 - 1) % 12
            return note
    raise('invalid root value')

def calculateLayer(node, ctx):
    global timeFactor

    if 'length' in node:
        if isinstance(node['length'],int):
            ctx.length = node['length'] * ctx.length
        elif isinstance(node['length'],str):
            ctx.length = eval(node['length']) * ctx.length
    if 'time' in node:
        timeFactor = node['time'] / ctx.length

    if 'pitch' in node:
        pitch = node['pitch']
        if 'zone' in pitch:
            ctx.pitch.zone = parseZone(pitch['zone'])
        if 'root' in pitch:
            ctx.pitch.root = parseRoot(pitch['root'])
        if 'pattern' in pitch:
            ctx.pitch.pattern = pitch['pattern']

    if 'trigger_note' in node:
        triggerNote = node['trigger_note']
        if triggerNote != None:
            offsets = (triggerNote if isinstance(triggerNote, list) else [triggerNote])
            for offset in offsets: 
                note = calculatePitch(ctx.pitch.root, ctx.pitch.zone, ctx.pitch.pattern, offset)
                midievents.append([ctx.time,'on',note])
                midievents.append([ctx.time+ctx.length,'off',note])

    if 'divs' in node:
        nextDivStart = ctx.time
        for divNode in calculateDivsNode(node['divs']):
            divCtx = deepcopy(ctx)
            divCtx.time = nextDivStart
            nextDivStart = calculateLayer(divNode, divCtx)
        return nextDivStart
    else:
        return ctx.time + ctx.length

def preProcessNode(node):
    if not isinstance(node,dict):
        return
    for k in list(node.keys()):
        if not isinstance(k,str):
            continue
        match = re.match(r'([^\.]+)\.(.+)', k)
        if match:
            leftToDot = match.group(1)
            rightToDot = match.group(2)
            if leftToDot not in node:
                node[leftToDot] = {}
            node[leftToDot][rightToDot] = node[k]
            del node[k]

    for k,v in node.items():
        preProcessNode(v)

with open('ctx_poc.yml', 'r') as f:
    rootNode = yaml.safe_load(f)
    preProcessNode(rootNode)
    ctx = Context(1.0,0,Pitch(60,5,patterns["major"]))
    lastDivisionEnd = calculateLayer(rootNode,ctx)

if timeFactor == None:
    raise 'time note found'

track = midi.Track()
midievents.sort(key = lambda e: e[0])
for i,n in enumerate(midievents):
    offset = (0 if i == 0 else midievents[i-1][0])
    time = int((n[0]-offset) * timeFactor * tickFactor)
    if n[1] == 'on':
        track.append(
            midi.NoteOnEvent(tick=time, velocity=127, pitch=n[2]))
    else:
        track.append(
            midi.NoteOffEvent(tick=time, pitch=n[2]))

eot = midi.EndOfTrackEvent(tick=10)

pattern = midi.Pattern()
pattern.append(track)
track.append(eot)
# Print out the pattern
print(pattern)
# Save the pattern to disk
midi.write_midifile("example.mid", pattern)