-- Each line of an operation's log says which step wrote it (null for a line written between steps), so clients
-- can show the log under its steps whatever the clock says.
ALTER TABLE operation_log ADD COLUMN step INTEGER;
