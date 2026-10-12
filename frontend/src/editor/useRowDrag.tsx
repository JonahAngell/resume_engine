import { useRef, useState, type PointerEvent } from "react";

type Session = {
  pointerId: number;
  listId: string;
  from: number;
  over: number;
  startY: number;
  moved: boolean;
};

export type RowDrag = {
  listId: string;
  from: number;
  over: number;
};

export function dragRowClass(drag: RowDrag | null, listId: string, index: number) {
  if (!drag || drag.listId !== listId || drag.from === drag.over) return "";
  if (drag.from === index) return "is-dragging";
  if (drag.over === index && drag.over < drag.from) return "drop-before";
  if (drag.over === index && drag.over > drag.from) return "drop-after";
  return "";
}

export function useRowDrag(
  onReorder: (listId: string, from: number, to: number) => void,
) {
  const sessionRef = useRef<Session | null>(null);
  const onReorderRef = useRef(onReorder);
  onReorderRef.current = onReorder;
  const [drag, setDrag] = useState<RowDrag | null>(null);

  const dropIndex = (listId: string, clientY: number, from: number) => {
    const rows = [...document.querySelectorAll<HTMLElement>("[data-drag-index]")].filter(
      (row) => row.dataset.dragList === listId,
    );
    let target = from;
    for (let i = 0; i < rows.length; i++) {
      if (i === from) continue;
      const rect = rows[i].getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      if (i < from && clientY < mid) return i;
      if (i > from && clientY > mid) target = i;
    }
    return target;
  };

  const start = (
    event: PointerEvent<HTMLButtonElement>,
    listId: string,
    index: number,
  ) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    sessionRef.current = {
      pointerId: event.pointerId,
      listId,
      from: index,
      over: index,
      startY: event.clientY,
      moved: false,
    };
  };

  const move = (event: PointerEvent<HTMLButtonElement>) => {
    const session = sessionRef.current;
    if (!session || event.pointerId !== session.pointerId) return;
    if (!session.moved && Math.abs(event.clientY - session.startY) < 4) return;
    session.moved = true;
    document.body.classList.add("section-reordering");
    const scroller = document.querySelector<HTMLElement>(".editor");
    if (scroller) {
      const bounds = scroller.getBoundingClientRect();
      if (event.clientY > bounds.bottom - 48) scroller.scrollTop += 14;
      else if (event.clientY < bounds.top + 48) scroller.scrollTop -= 14;
    }
    const over = dropIndex(session.listId, event.clientY, session.from);
    if (over === session.over && drag?.listId === session.listId) return;
    session.over = over;
    setDrag({ listId: session.listId, from: session.from, over });
  };

  const end = (event: PointerEvent<HTMLButtonElement>) => {
    const session = sessionRef.current;
    if (!session || event.pointerId !== session.pointerId) return;
    sessionRef.current = null;
    document.body.classList.remove("section-reordering");
    setDrag(null);
    if (!session.moved || session.over === session.from) return;
    onReorderRef.current(session.listId, session.from, session.over);
  };

  const nudge = (listId: string, from: number, to: number) => {
    if (from === to) return;
    onReorderRef.current(listId, from, to);
  };

  return { drag, start, move, end, nudge };
}

export function DragHandle({
  label,
  listId,
  index,
  count,
  drag,
}: {
  label: string;
  listId: string;
  index: number;
  count: number;
  drag: ReturnType<typeof useRowDrag>;
}) {
  return (
    <button
      type="button"
      className="drag-handle bullet-drag-handle"
      aria-label={`Drag ${label}`}
      onPointerDown={(event) => drag.start(event, listId, index)}
      onPointerMove={drag.move}
      onPointerUp={drag.end}
      onPointerCancel={drag.end}
      onKeyDown={(event) => {
        if (event.key === "ArrowUp" && index > 0) {
          event.preventDefault();
          drag.nudge(listId, index, index - 1);
        }
        if (event.key === "ArrowDown" && index < count - 1) {
          event.preventDefault();
          drag.nudge(listId, index, index + 1);
        }
      }}
    >
      ⠿
    </button>
  );
}
