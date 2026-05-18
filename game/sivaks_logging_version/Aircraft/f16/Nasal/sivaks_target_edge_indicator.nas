# Green marker on the screen border pointing toward the active target.
# Uses Canvas desktop (drawn inside FlightGear — no telnet / external overlay).

var SIVAKS_DEG2RAD = 0.017453292519943295;
var SIVAKS_RAD2DEG = 57.29577951308232;

var SivaksTargetEdge = {
    _dot: nil,
    _timer: nil,

    _screenSize: func() {
        var w = getprop("/sim/current-view/viewport-width");
        var h = getprop("/sim/current-view/viewport-height");
        if (w == nil or h == nil or w < 200 or h < 200) {
            w = getprop("/sim/startup/xsize");
            h = getprop("/sim/startup/ysize");
        }
        if (w == nil or h == nil or w < 200 or h < 200)
            return [1920, 1080];
        return [w, h];
    },

    _relBearing: func(heading_deg, bearing_deg) {
        var d = bearing_deg - heading_deg;
        while (d > 180)
            d -= 360;
        while (d < -180)
            d += 360;
        return d;
    },

    _edgeXY: func(rel_bearing_deg, elev_deg, w, h, margin) {
        var br = rel_bearing_deg * SIVAKS_DEG2RAD;
        var el = elev_deg * SIVAKS_DEG2RAD;
        if (el > 89 * SIVAKS_DEG2RAD)
            el = 89 * SIVAKS_DEG2RAD;
        if (el < -89 * SIVAKS_DEG2RAD)
            el = -89 * SIVAKS_DEG2RAD;

        var dx = math.sin(br) * math.cos(el);
        var dy = math.sin(el);
        # Target straight ahead: top center (canvas Y grows downward).
        if (math.abs(dx) < 0.000001 and math.abs(dy) < 0.000001) {
            dx = 0;
            dy = 1;
        }

        var scale = 1.0 / math.max(math.abs(dx), math.abs(dy));
        var nx = 0.5 + 0.5 * dx * scale;
        var ny = 0.5 - 0.5 * dy * scale;
        var x = margin + nx * (w - 2 * margin);
        var y = margin + ny * (h - 2 * margin);
        return [x, y];
    },

    init: func() {
        if (me._dot != nil)
            return;

        var desktop = canvas.getDesktop();
        if (desktop == nil) {
            printlog("SivaksTargetEdge: canvas desktop unavailable");
            return;
        }

        me._dot = desktop.createChild("text")
            .setText("●")
            .setFontSize(72, 1.0)
            .setColor(0.1, 1.0, 0.2, 1.0)
            .setAlignment("center-center")
            .setTranslation(100, 100)
            .setVisible(0);
        me._dot.set("z-index", 99999);

        me._timer = maketimer(0.1, func {
            SivaksTargetEdge.update();
        });
        me._timer.start();
        printlog("SivaksTargetEdge: edge marker active");
    },

    shutdown: func() {
        if (me._timer != nil) {
            me._timer.stop();
            me._timer = nil;
        }
        if (me._dot != nil) {
            me._dot.setVisible(0);
            me._dot = nil;
        }
    },

    update: func() {
        if (me._dot == nil)
            return;

        var finished = getprop("/algorithm/game/finished");
        if (finished != nil and finished > 0) {
            me._dot.setVisible(0);
            return;
        }

        var tgtLat = getprop("/algorithm/game/balloon-lat");
        var tgtLon = getprop("/algorithm/game/balloon-lon");
        var tgtAlt = getprop("/algorithm/game/balloon-alt");
        if (tgtLat == nil or tgtLon == nil or tgtAlt == nil) {
            me._dot.setVisible(0);
            return;
        }

        var ac = geo.aircraft_position();
        var acAlt = getprop("/position/altitude-ft");
        if (acAlt == nil)
            acAlt = 0;

        var heading = getprop("/orientation/true-heading-deg");
        if (heading == nil)
            heading = getprop("/orientation/heading-deg");
        if (heading == nil)
            heading = 0;

        var target = geo.Coord.new().set_latlon(tgtLat, tgtLon);
        target.set_alt(tgtAlt / globals.M2FT);

        var bearing = ac.course_to(target);
        var rel = me._relBearing(heading, bearing);

        var horiz_ft = ac.direct_distance_to(target) * globals.M2FT;
        var elev = 0;
        if (horiz_ft > 50)
            elev = math.atan2(tgtAlt - acAlt, horiz_ft) * SIVAKS_RAD2DEG;

        var sz = me._screenSize();
        var xy = me._edgeXY(rel, elev, sz[0], sz[1], 36);

        me._dot.setTranslation(xy[0], xy[1]);
        me._dot.setVisible(1);
    },
};

# Tutorial checks via globals — bare symbol lookup throws if the module was not loaded yet.
globals.SivaksTargetEdge = SivaksTargetEdge;
