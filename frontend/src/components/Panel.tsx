import type { ReactNode } from 'react';

export function Panel({ title, eyebrow, action, children, className = '' }: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>
        {action}
      </div>
      {children}
    </section>
  );
}
