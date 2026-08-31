import { useCallback, useState } from "react";

export function useToggle(initial = false): [boolean, () => void, (value: boolean) => void] {
  const [on, setOn] = useState(initial);

  const toggle = useCallback(() => {
    setOn((prev) => !prev);
  }, []);

  const set = useCallback((value: boolean) => {
    setOn(value);
  }, []);

  return [on, toggle, set];
}
