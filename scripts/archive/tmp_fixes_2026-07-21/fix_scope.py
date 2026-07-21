#!/usr/bin/env python3
"""Fix the Quant Team init scoping issue — bootQuantTeam not visible for addEventListener"""
B = "/root/nexustrader"
with open(f"{B}/dashboard/enhancer.js") as f:
    js = f.read()

# The bug: (function bootQuantTeam() { ... addEventListener('DOMContentLoaded', bootQuantTeam) })()
# bootQuantTeam is a named function expression, its name is only visible inside itself
# But addEventListener tries to reference it from the outer scope → ReferenceError

# Solution: use a proper named function declaration + immediate call
old_boot = """    (function bootQuantTeam() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootQuantTeam);
            return;
        }
        _runQuantTeam();
    })();
    
    function _runQuantTeam() {
        var triggers = {"""

new_boot = """    function bootQuantTeam() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootQuantTeam);
            return;
        }
        _runQuantTeam();
    }
    bootQuantTeam();
    
    function _runQuantTeam() {
        var triggers = {"""

js = js.replace(old_boot, new_boot)

opens = js.count('{')
closes = js.count('}')
print(f"Braces: {opens}/{closes} {'OK' if opens==closes else 'MISMATCH'}")

with open(f"{B}/dashboard/enhancer.js", "w") as f:
    f.write(js)
print("Fixed: bootQuantTeam now a proper function declaration (scoped correctly for addEventListener)")
