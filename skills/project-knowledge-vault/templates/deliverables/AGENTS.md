# Project Deliverables - how this folder works

This folder holds the documents a project delivers to the people who build and run what it describes: solution designs, architecture decision records, and the guides and runbooks for the system as it is today. It is written to be copied as a whole into a code repository's documentation folder, so every file reads on its own and every link in it is a relative markdown link.

## What this folder holds

- Files at the top level ending in `-guide.md` or `-runbook.md` describe how the system works today and how to do tasks on it.
- `solution-designs/` holds one design per feature or change, named `SD-NNN-<slug>.md`. A solution design says how the work will be built.
- `adrs/` holds one decision per record, named `ADR-NNN-<slug>.md`. A decision record says what was decided, when and why, and which options were set aside.
- `templates/` holds the starting points for a new solution design and a new decision record.
- `index.md` lists every document with one line on what it covers. Start there.
- `log.md` lists what changed in this folder, newest first.

## Reading

1. Find the document in `index.md`, then the section that answers the question.
2. For how things work today, read a guide. A decision record explains why, and a later record or guide can describe a newer state. When the code disagrees with any document, the code is correct.
3. Cite the file and section each answer comes from, and say so when no document answers the question.

## Editing

1. Before starting a new document, extend the one that already covers the topic.
2. Start a solution design or a decision record from `templates/`, numbered one past the highest in its folder, and add its line to `index.md` in the same change.
3. Add one line to `log.md` for every change, under a heading for that day's date, naming the file and what changed.
4. A solution design stays current until its work ships. An accepted decision record is not rewritten: a change of decision is a new record that names the one it supersedes.
5. Write settled content for the people who build and run the system. Working notes, open questions and evidence stay with the project's notes, not here.
6. Keep secrets, credentials, hostnames, internal IDs and personal details out of every file.

## Conventions

- Links within the folder are relative markdown links to a file and a section anchor, such as a link to the `decision` section of a record in `adrs/`, never wikilinks.
- Section headings are lowercase and hyphenated, so their anchors stay stable. A heading rename breaks every link into it, so repoint those links in the same change.
- Names in angle brackets, such as `<env>`, are placeholders the reader fills in.
- Write in plain, full sentences with American spelling.
