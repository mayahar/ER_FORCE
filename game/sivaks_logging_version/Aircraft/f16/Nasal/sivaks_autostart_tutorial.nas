# Sivaks automation: auto-start an XML tutorial by name (Help -> Tutorials).
# Enabled from logging_fg_start_ver5.py via:
#   --prop:/sim/sivaks/autostart-tutorial-enabled=true
#   --prop:/sim/sivaks/autostart-tutorial=CorrActions DEFAULT

props.globals.initNode("/sim/sivaks/autostart-tutorial-enabled", 0, "BOOL");
props.globals.initNode("/sim/sivaks/autostart-tutorial", "CorrActions DEFAULT", "STRING");

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
