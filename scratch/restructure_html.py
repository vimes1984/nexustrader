import re

with open("/home/chris/nexustrader/dashboard/index.html", "r") as f:
    html = f.read()

# Let's find the bottom-content block
pattern = r'(<!-- Lower Panels Grid -->\s*<section class="bottom-content" aria-label="Trade History and Statistical Analysis">.*?</section>)'
match = re.search(pattern, html, re.DOTALL)
if not match:
    print("Could not find bottom-content block!")
    exit(1)

bottom_content = match.group(1)

# Now, remove the bottom-content block from its original position
html_cleaned = html.replace(bottom_content, "")

# Now find where the chart-panel ends (</article> followed by sidebar-container)
# Note that we previously wrapped it in <div class="main-left-column">
# So we want to find </article>\s*?(?=\s*<div class="sidebar-container")
target_pos = re.search(r'</article>\s*(?=\s*<div class="sidebar-container")', html_cleaned)
if not target_pos:
    print("Could not find end of chart-panel!")
    exit(1)

end_index = target_pos.end()

# Insert the bottom-content block and a closing </div> for main-left-column
new_insert = "\n\n            " + bottom_content + "\n        </div>"

html_final = html_cleaned[:end_index] + new_insert + html_cleaned[end_index:]

with open("/home/chris/nexustrader/dashboard/index.html", "w") as f:
    f.write(html_final)

print("Restructured index.html successfully!")
