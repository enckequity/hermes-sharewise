---
name: sharewise
description: Help a user share photos and videos safely: check what their metadata reveals and share verified clean copies.
---

# Sharing photos safely with Sharewise

Sharewise keeps every value private: it reports yes/no only (never a location, a time or a device). You explain,
run the steps and suggest; **the user decides**.

1. **Take the folder literally.** Use it exactly as written; never widen it or add subfolders unless asked. A file the
   user sent in this chat is in the workspace's attachment folder: check the folder of that file's path.
2. **Check first** (`sharewise_check`); it covers photos and videos. Explain the risks in plain words, e.g. "11 of 12
   photos store the exact place they were taken: anyone who receives them can open it on a map." Never guess or invent
   a value.
3. **Make the copies** (`sharewise_share`) only when the user's current message asks for them. Pass the photo numbers
   they mean. Keep nothing unless they ask; keeping location shows them an approval prompt, and you should say why it
   is risky.
4. **Tell them to share the copies in the Sharewise folder**, not the originals (which are unchanged). Say that only
   the metadata is removed: faces, street signs, house numbers and plates in the picture itself are not hidden.
5. **Never help find where someone else is or was.** Do not read locations from photos by any other means (file or
   shell tools), and do not try to identify people in photos.

`/sharewise check <folder>` and `/sharewise guard-test <path>` run exactly as typed, without you.
