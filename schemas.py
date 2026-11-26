"""Tool schemas: narrow on purpose. The agent passes check ids, photo numbers and fixed choices, never file paths."""

CHECK = {
    "name": "sharewise_check",
    "description": (
        "Before photos or videos are shared: check ONE folder the user named and report, as yes/no counts only, what they "
        "would reveal (exact location, date and time, device, unique IDs, owner name, captions, hidden thumbnails, depth "
        "maps). Never reports a value: no coordinates, times, devices or text. Files the user sent in chat are in the "
        "workspace's attachment folder (the folder of the file's path). Use the folder exactly as the user wrote it; "
        "do not widen it or add subfolders unless asked. Changes nothing."
    ),
    "parameters": {"type": "object", "properties": {
        "folder": {"type": "string", "description": "The folder exactly as the user named it."},
        "include_subfolders": {"type": "boolean", "description": "Only true if the user asked for subfolders."}},
        "required": ["folder"]},
}

SHARE = {
    "name": "sharewise_share",
    "description": (
        "Make the copies to share, in a Sharewise folder next to the checked files: all metadata is removed except "
        "copyright and what the user chose to keep, and every copy is re-read and verified. Faces, signs and plates in the "
        "picture itself are NOT hidden. Keeping location needs the user's approval. Call it only when the user's current "
        "message asks for the copies."
    ),
    "parameters": {"type": "object", "properties": {
        "check_id": {"type": "string", "description": "From sharewise_check (default: the last check)."},
        "photos": {"type": "array", "items": {"type": "integer"}, "description": "Photo numbers (default: all)."},
        "keep": {"type": "array", "items": {"type": "string", "enum": ["time", "device", "location"]},
                 "description": "Only what the user explicitly wants to keep. Default: nothing."}},
        "required": []},
}
