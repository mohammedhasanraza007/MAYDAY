---
triggers: [file, write, create, save, document, report, csv, json, code, script, project, scaffold]
---
FILE OPERATION RULES:
- file_write requires non-empty content (minimum 10 characters).
- Always confirm the target path before writing; never write to system directories.
- For multi-file projects, use scaffold tool, not individual file_write calls.
- After writing a file, confirm with file_read to verify content was saved correctly.
- Code files must include a shebang or import header appropriate to the language.
- If writing fails, check the error message for path or permission issues before retrying.
