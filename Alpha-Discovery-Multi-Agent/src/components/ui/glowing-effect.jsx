import React, { useRef, useState, useCallback } from 'react';
import { cn } from '@/lib/utils';

export function GlowingEffect({
  children,
  className,
  glowColor = 'rgba(37, 99, 235, 0.45)', // Electric Blue base
  glowColorSecondary = 'rgba(124, 58, 237, 0.35)', // Electric Purple base
  spread = 600,
  borderWidth = 1,
  disabled = false,
  ...props
}) {
  const containerRef = useRef(null);
  const [isHovered, setIsHovered] = useState(false);
  const [coords, setCoords] = useState({ x: 0, y: 0 });

  const handleMouseMove = useCallback((e) => {
    if (!containerRef.current || disabled) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    setCoords({ x, y });

    // Directly set CSS variables for high-performance 60fps movement
    containerRef.current.style.setProperty('--mouse-x', `${x}px`);
    containerRef.current.style.setProperty('--mouse-y', `${y}px`);
  }, [disabled]);

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn('relative group rounded-2xl transition-all duration-300', className)}
      {...props}
    >
      {/* Outer Glowing Radial Border */}
      <div
        className="pointer-events-none absolute -inset-[1px] rounded-2xl transition-opacity duration-500 z-0"
        style={{
          opacity: isHovered ? 1 : 0,
          background: `radial-gradient(${spread}px circle at var(--mouse-x, 50%) var(--mouse-y, 50%), ${glowColor}, ${glowColorSecondary} 40%, transparent 80%)`,
          padding: `${borderWidth}px`,
          WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
          WebkitMaskComposite: 'xor',
          maskComposite: 'exclude',
        }}
      />

      {/* Subtle Inner Glow Background Spotlight */}
      <div
        className="pointer-events-none absolute inset-0 rounded-2xl transition-opacity duration-500 z-0 overflow-hidden"
        style={{
          opacity: isHovered ? 0.15 : 0,
          background: `radial-gradient(${spread * 0.7}px circle at var(--mouse-x, 50%) var(--mouse-y, 50%), ${glowColor}, transparent 70%)`,
        }}
      />

      {/* Card Content Container */}
      <div className="relative z-10 h-full w-full rounded-2xl">
        {children}
      </div>
    </div>
  );
}
