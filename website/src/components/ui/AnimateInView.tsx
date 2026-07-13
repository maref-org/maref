import { useRef, useState, useEffect, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
  delay?: number;
  x?: number;
  y?: number;
  duration?: number;
  once?: boolean;
  margin?: string;
  as?: "div" | "section";
  style?: React.CSSProperties;
}

function useIntersectionInView(options?: {
  once?: boolean;
  margin?: string;
}): [React.RefObject<HTMLDivElement | null>, boolean] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (options?.once !== false) observer.disconnect();
        }
      },
      { rootMargin: options?.margin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [options?.once, options?.margin]);

  return [ref, inView];
}

export function AnimateInView({
  children,
  className = "",
  delay = 0,
  x = 0,
  y = 30,
  duration = 0.6,
  once = true,
  margin = "-80px",
  as: Tag = "div",
  style,
}: Props) {
  const [ref, inView] = useIntersectionInView({ once, margin });

  return (
    <Tag
      ref={ref}
      className={className}
      style={{
        ...style,
        opacity: inView ? 1 : 0,
        transform: inView ? "translate(0,0)" : `translate(${x}px,${y}px)`,
        transition: `opacity ${duration}s ease-out, transform ${duration}s ease-out`,
        transitionDelay: `${delay}s`,
      }}
    >
      {children}
    </Tag>
  );
}

export function FadeIn({
  children,
  className = "",
  delay = 0,
  duration = 0.8,
  style,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  duration?: number;
  style?: React.CSSProperties;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 50);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      className={className}
      style={{
        ...style,
        opacity: mounted ? 1 : 0,
        transform: mounted ? "translate(0,0)" : "translateY(40px)",
        transition: `opacity ${duration}s ease-out, transform ${duration}s ease-out`,
        transitionDelay: `${delay}s`,
      }}
    >
      {children}
    </div>
  );
}
