# Rotating arrow on screen border when target is off-screen (hidden when in view).

var SIVAKS_DEG2RAD = 0.017453292519943295;

var _mat_vec_mult = func(m, v) {
    return [
        m[0] * v[0] + m[1] * v[1] + m[2] * v[2] + m[3] * v[3],
        m[4] * v[0] + m[5] * v[1] + m[6] * v[2] + m[7] * v[3],
        m[8] * v[0] + m[9] * v[1] + m[10] * v[2] + m[11] * v[3],
        m[12] * v[0] + m[13] * v[1] + m[14] * v[2] + m[15] * v[3],
    ];
};

var _quat_conj = func(q) {
    return [q[0], -q[1], -q[2], -q[3]];
};

var _quat_mult = func(q1, q2) {
    return [
        q1[0] * q2[0] - q1[1] * q2[1] - q1[2] * q2[2] - q1[3] * q2[3],
        q1[0] * q2[1] + q1[1] * q2[0] - q1[2] * q2[3] + q1[3] * q2[2],
        q1[0] * q2[2] + q1[1] * q2[3] + q1[2] * q2[0] - q1[3] * q2[1],
        q1[0] * q2[3] - q1[1] * q2[2] + q1[2] * q2[1] + q1[3] * q2[0],
    ];
};

var _rot_vec3_by_quat = func(v, q) {
    var qv = [0, v[0], v[1], v[2]];
    var qr = _quat_mult(_quat_mult(q, qv), _quat_conj(q));
    return [qr[1], qr[2], qr[3]];
};

var _proj_matrix = func(fovy, aspect, znear, zfar) {
    var f = 1.0 / math.tan(fovy / 2.0);
    var zdiff = znear - zfar;
    return [
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (zfar + znear) / zdiff, 2.0 * zfar * znear / zdiff,
        0, 0, -1, 0,
    ];
};

var _geo_to_screen = func(geocoord) {
    var screen_w = getprop("/sim/startup/xsize");
    var screen_h = getprop("/sim/startup/ysize");
    if (screen_w == nil or screen_h == nil or screen_w < 100)
        return nil;

    var aspect = screen_w / screen_h;
    var fovx = getprop("/sim/current-view/field-of-view");
    if (fovx == nil)
        fovx = 55;
    fovx = fovx * SIVAKS_DEG2RAD;
    var fovy = 2.0 * math.atan2(math.tan(fovx / 2.0) / aspect, 1.0);

    var znear = getprop("/sim/rendering/camera-group/znear");
    var zfar = getprop("/sim/rendering/camera-group/zfar");
    if (znear == nil) znear = 1.0;
    if (zfar == nil) zfar = 120000.0;

    var proj_mat = _proj_matrix(fovy, aspect, znear, zfar);
    var geocoord_pos = geocoord.xyz();
    var viewer_pos = [
        getprop("/sim/current-view/viewer-x-m"),
        getprop("/sim/current-view/viewer-y-m"),
        getprop("/sim/current-view/viewer-z-m"),
    ];
    if (viewer_pos[0] == nil)
        return nil;

    var diff_vec = [
        geocoord_pos[0] - viewer_pos[0],
        geocoord_pos[1] - viewer_pos[1],
        geocoord_pos[2] - viewer_pos[2],
    ];
    var quat_viewer_rot = [
        getprop("/sim/current-view/raw-orientation[0]"),
        getprop("/sim/current-view/raw-orientation[1]"),
        getprop("/sim/current-view/raw-orientation[2]"),
        getprop("/sim/current-view/raw-orientation[3]"),
    ];
    if (quat_viewer_rot[0] == nil)
        return nil;

    var vec_view_space = _rot_vec3_by_quat(diff_vec, quat_viewer_rot);
    append(vec_view_space, 1.0);
    var vec_proj = _mat_vec_mult(proj_mat, vec_view_space);
    if (math.abs(vec_proj[3]) < 0.000001)
        return nil;

    var device_coords_xy = [vec_proj[0] / vec_proj[3], vec_proj[1] / vec_proj[3]];
    var norm_coords_xy = [
        (device_coords_xy[0] + 1.0) * 0.5,
        (device_coords_xy[1] + 1.0) * 0.5,
    ];
    var screen_coords_xy = [
        norm_coords_xy[0] * screen_w,
        norm_coords_xy[1] * screen_h,
    ];
    return {
        "screen_xy": screen_coords_xy,
        "is_behind": vec_view_space[2] > 0.0,
        "w": screen_w,
        "h": screen_h,
    };
};

var SivaksTargetEdge = {
    _arrow: nil,
    _timer: nil,

    _flip_y: func(py, h) {
        return h - py;
    },

    _clamp_to_edge: func(px, py, w, h, margin) {
        var cx = w * 0.5;
        var cy = h * 0.5;
        var dx = px - cx;
        var dy = py - cy;
        if (math.abs(dx) < 1 and math.abs(dy) < 1) {
            return [cx, h - margin];
        }
        var scale = 1.0 / math.max(math.abs(dx), math.abs(dy));
        var nx = 0.5 + 0.5 * dx * scale;
        var ny = 0.5 + 0.5 * dy * scale;
        return [
            margin + nx * (w - 2 * margin),
            margin + ny * (h - 2 * margin),
        ];
    },

    _point_angle: func(from_x, from_y, to_x, to_y) {
        return math.atan2(to_y - from_y, to_x - from_x);
    },

    init: func() {
        if (me._arrow != nil)
            return;

        var desktop = canvas.getDesktop();
        if (desktop == nil) {
            print("SivaksTargetEdge: canvas desktop unavailable, retrying...");
            settimer(func { SivaksTargetEdge.init(); }, 1.0);
            return;
        }

        # Chevron arrow (local +X = tip); rotated toward target on screen edge.
        me._arrow = desktop.createChild("path", "sivaks-target-arrow")
            .move(44, 0)
            .line(-24, -28)
            .line(-10, 0)
            .line(-24, 28)
            .close()
            .setColorFill(0.1, 1.0, 0.2, 0.95)
            .setColor(0.05, 0.65, 0.12, 1.0)
            .setTranslation(80, 80);
        me._arrow.setCenter(0, 0);
        me._arrow.set("z-index", 99999);

        me._timer = maketimer(0.02, func {
            SivaksTargetEdge.update();
        });
        me._timer.start();
        print("SivaksTargetEdge: edge arrow active");
    },

    shutdown: func() {
        if (me._timer != nil) {
            me._timer.stop();
            me._timer = nil;
        }
        if (me._arrow != nil) {
            me._arrow.setVisible(0);
            me._arrow = nil;
        }
    },

    update: func() {
        if (me._arrow == nil)
            return;

        var finished = getprop("/algorithm/game/finished");
        if (finished != nil and finished > 0) {
            me._arrow.setVisible(0);
            return;
        }

        var tgtLat = getprop("/algorithm/game/balloon-lat");
        var tgtLon = getprop("/algorithm/game/balloon-lon");
        var tgtAlt = getprop("/algorithm/game/balloon-alt");
        if (tgtLat == nil or tgtLon == nil or tgtAlt == nil) {
            me._arrow.setVisible(0);
            return;
        }

        var target = geo.Coord.new().set_latlon(tgtLat, tgtLon);
        target.set_alt(tgtAlt / globals.M2FT);

        var proj = _geo_to_screen(target);
        if (proj == nil) {
            me._arrow.setVisible(0);
            return;
        }

        var w = proj.w;
        var h = proj.h;
        var margin = 44;
        var px = proj.screen_xy[0];
        var py = me._flip_y(proj.screen_xy[1], h);
        var on_screen =
            !proj.is_behind and
            px >= margin and px <= (w - margin) and
            py >= margin and py <= (h - margin);

        if (on_screen) {
            me._arrow.setVisible(0);
        } else {
            var edge = me._clamp_to_edge(px, py, w, h, margin);
            var angle = me._point_angle(edge[0], edge[1], px, py);
            if (proj.is_behind)
                angle = angle + math.pi;
            me._arrow.setTranslation(edge[0], edge[1]);
            me._arrow.setRotation(angle);
            me._arrow.setVisible(1);
        }
    },
};

globals.SivaksTargetEdge = SivaksTargetEdge;
