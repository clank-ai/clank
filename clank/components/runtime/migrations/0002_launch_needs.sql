-- What a launch needed free to start, when its engine says (design 0001 §3.6): NInfer plans its memory and reserves
-- more than it touches, so its next estimate learns from what it needed, not from what it took (found 2026-10-13).
ALTER TABLE launches ADD COLUMN needed_mib INTEGER;
