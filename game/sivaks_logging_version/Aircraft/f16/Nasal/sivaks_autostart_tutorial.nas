# Sivaks automation: auto-start an XML tutorial by name (Help -> Tutorials).
# Enabled from logging_fg_start_ver5.py via:
#   --prop:/sim/sivaks/autostart-tutorial-enabled=true
#   --prop:/sim/sivaks/autostart-tutorial=CorrActions DEFAULT

props.globals.initNode("/sim/sivaks/autostart-tutorial-enabled", 0, "BOOL");
props.globals.initNode("/sim/sivaks/autostart-tutorial", "CorrActions DEFAULT", "STRING");
props.globals.initNode("/sim/sivaks/corractions-reset-request", 0, "INT");
props.globals.initNode("/algorithm/game/retry-count", 0, "INT");

globals.sivaksMainTutorialLoaded = 0;
globals.sivaksWasAirborne = 0;
globals.sivaksCrashResetBusy = 0;
globals.sivaksLowSince = nil;
globals.sivaksCrashExitGraceSec = 20.0;

globals.sivaksApplyCruiseAttitude = func() {
    setprop("/controls/engines/throttle-all", 0.85);
    setprop("/controls/engines/engine[0]/throttle", 0.85);
    setprop("/controls/flight/elevator", 0);
    setprop("/controls/flight/elevator-trim", 0.06);
    setprop("/controls/flight/aileron", 0);
    setprop("/controls/flight/rudder", 0);
    setprop("/controls/gear/gear-down", 0);
    setprop("/controls/gear/brake-parking", 0);
};

# Remove all existing CorrActions targets (balloon + bullseye + aim dot).
globals.sivaksPurgeCorrTargets = func() {
    var root = props.globals.getNode("/ai/models");
    if (root == nil)
        return;
    var ids_to_remove = [];
    var types = ["static", "aircraft", "multiplayer", "wingman"];
    foreach (var typ; types)
    {
        foreach (var m; root.getChildren(typ))
        {
            var cs = m.getNode("callsign");
            var model = m.getNode("model");
            if (model == nil)
                model = m.getNode("model-path");
            var cs_v = (cs != nil) ? cs.getValue() : "";
            var model_v = (model != nil) ? model.getValue() : "";
            var is_ours = 0;
            if (cs_v != "" and (
                find(cs_v, "sivaks_bsign") >= 0 or
                find(cs_v, "ca_corr_") >= 0))
                is_ours = 1;
            if (!is_ours and model_v != "" and (
                find(model_v, "ca_sivaks_balloon") >= 0 or
                find(model_v, "ca_sivaks_bullseye") >= 0 or
                find(model_v, "ca_sivaks_aim_dot") >= 0))
                is_ours = 1;
            if (!is_ours)
                continue;
            var idn = m.getNode("id");
            if (idn != nil)
                append(ids_to_remove, idn.getValue());
        }
    }
    foreach (var rid; ids_to_remove)
        fgcommand("remove-aiobject", props.Node.new({"id": rid}));
};

# Restore airframe visuals after crash (must not throw — called after reposition).
globals.sivaksRepairAircraft = func() {
    setprop("/sim/crashed", 0);
    setprop("/damage/sounds/explode-on", 0);
    setprop("/damage/sounds/crash-on", 0);
    setprop("/damage/sounds/detach-on", 0);
    setprop("/damage/sounds/crack-on", 0);
    setprop("/damage/sounds/creaking-on", 0);
    setprop("/damage/sounds/water-crash-on", 0);
    setprop("/damage/sounds/crack-volume", 0);
    setprop("/damage/sounds/creaking-volume", 0);
    setprop("/damage/fire/serviceable", 1);
    setprop("/controls/engines/engine[0]/on-fire", 0);
    setprop("/controls/engines/engine[1]/on-fire", 0);
    setprop("/controls/engines/engine[2]/on-fire", 0);
    setprop("/controls/engines/engine[3]/on-fire", 0);

    call(func {
        if (contains(globals, "FailureMgr") and FailureMgr._failmgr != nil) {
            var failure_modes = FailureMgr._failmgr.failure_modes;
            foreach (var failure_mode_id; keys(failure_modes))
                FailureMgr.set_failure_level(failure_mode_id, 0);
        }
    }, nil, var _repair_err = []);

    call(func {
        if (contains(globals, "crashCode") and crashCode != nil)
            crashCode.repair();
    }, nil, var _crash_repair_err = []);
};

globals.sivaksRepositionToCorrActions = func() {
    if (globals.sivaksCrashResetBusy)
        return;
    globals.sivaksCrashResetBusy = 1;

    var retry_count = getprop("/algorithm/game/retry-count");
    if (retry_count == nil)
        retry_count = 0;
    setprop("/algorithm/game/retry-count", retry_count + 1);

    globals.sivaksPurgeCorrTargets();
    setprop("/sim/crashed", 0);
    setprop("/sim/freeze/master", 0);
    setprop("/sim/presets/airport-id", "PHTO");
    setprop("/sim/presets/on-ground", 0);
    setprop("/sim/presets/latitude-deg", 19.72415017471669);
    setprop("/sim/presets/longitude-deg", -155.0518970894882);
    setprop("/sim/presets/altitude-ft", 2000);
    setprop("/sim/presets/heading-deg", 0);
    setprop("/sim/presets/airspeed-kt", 350);
    setprop("/sim/presets/glideslope-deg", 0);
    setprop("/sim/presets/offset-azimuth-deg", 0);
    setprop("/sim/presets/offset-distance-nm", 0);
    fgcommand("reposition");
    globals.sivaksApplyCruiseAttitude();
    setprop("/sim/messages/copilot", "RETRY");

    settimer(func {
        globals.sivaksPurgeCorrTargets();
        globals.sivaksRepairAircraft();
        globals.sivaksApplyCruiseAttitude();
        globals.sivaksCrashResetBusy = 0;
    }, 0.5);
};

globals.sivaksRequestFullCrashReset = func() {
    var reset_request = getprop("/sim/sivaks/corractions-reset-request");
    if (reset_request == nil)
        reset_request = 0;
    setprop("/sim/sivaks/corractions-reset-request", reset_request + 1);
};

# Returns 1 if the aircraft is down after having been airborne.
var _sivaksIsFallen = func() {
    if (!globals.sivaksWasAirborne)
        return 0;
    var crashed = getprop("/sim/crashed");
    if (crashed != nil and crashed > 0)
        return 1;
    var agl = getprop("/position/altitude-agl-ft");
    var alt = getprop("/position/altitude-ft");
    if (agl != nil and agl < 200)
        return 1;
    if (alt != nil and alt < 200)
        return 1;
    return 0;
};

var _sivaksIsRecovered = func() {
    var agl = getprop("/position/altitude-agl-ft");
    if (agl != nil and agl > 500)
        return 1;
    var alt = getprop("/position/altitude-ft");
    if (alt != nil and alt > 1500)
        return 1;
    return 0;
};

var _crash_poll = func() {
    if (globals.sivaksCrashResetBusy)
        return;

    var agl = getprop("/position/altitude-agl-ft");
    if (agl != nil and agl > 150)
        globals.sivaksWasAirborne = 1;

    if (_sivaksIsRecovered()) {
        globals.sivaksLowSince = nil;
        return;
    }

    if (!_sivaksIsFallen())
        return;

    var sim_t = getprop("/sim/time/elapsed-sec");
    if (sim_t == nil)
        sim_t = 0;
    if (globals.sivaksLowSince == nil)
        globals.sivaksLowSince = sim_t;

    if ((sim_t - globals.sivaksLowSince) >= globals.sivaksCrashExitGraceSec) {
        setprop("/sim/messages/copilot", "SESSION END");
        fgcommand("exit");
        return;
    }

    if (globals.sivaksMainTutorialLoaded)
        globals.sivaksRequestFullCrashReset();
    else
        globals.sivaksRepositionToCorrActions();
};

var _crash_poll_timer = maketimer(0.05, _crash_poll);
_crash_poll_timer.start();

setlistener("/sim/crashed", func(node) {
    if (node == nil or !node.getValue())
        return;
    if (globals.sivaksCrashResetBusy)
        return;
    _crash_poll();
}, 0, 0);

var _autostart_done = 0;
var _was_frozen = 0;

var _start = func {
    if (_autostart_done)
        return;
    if (!getprop("/sim/sivaks/autostart-tutorial-enabled"))
        return;
    _autostart_done = 1;

    var name = getprop("/sim/sivaks/autostart-tutorial");
    if (name == nil or size(name) < 1)
        name = "CorrActions DEFAULT";

    # Hide the brief pre-tutorial state by freezing until startTutorial() runs.
    _was_frozen = getprop("/sim/freeze/master") ? 1 : 0;
    setprop("/sim/freeze/master", 1);

    setprop("/sim/tutorials/current-tutorial", name);
    setprop("/nasal/tutorial/enabled", 1);
    settimer(func {
        tutorial.startTutorial();
        if (!_was_frozen)
            setprop("/sim/freeze/master", 0);
    }, 0);
};

var _fdm_listener = nil;
_fdm_listener = setlistener("/sim/signals/fdm-initialized", func (node) {
    if (!node.getBoolValue())
        return;
    if (_fdm_listener != nil)
        removelistener(_fdm_listener);
    _fdm_listener = nil;
    # Slightly longer delay on first cold start so AI/balloon scenario + tutorials are registered before startTutorial().
    settimer(_start, 3.2);
}, 1, 0);
