import React, { useMemo, useState, useEffect, useRef } from 'react';

interface CircuitBackgroundProps {
  color?: string; // 'orange' | 'blue' | 'purple'
}

interface InteractiveParticle {
  id: number;
  x: number;
  y: number;
  baseX: number;
  baseY: number;
  size: number;
  opacity: number;
  speed: number;
}

// 添加动画样式
const animationStyles = document.createElement('style');
animationStyles.textContent = `
  @keyframes gradientPulse {
    0%, 100% { opacity: 0.45; transform: scale(1); }
    50% { opacity: 0.55; transform: scale(1.02); }
  }
  
  @keyframes floatUp {
    0% { transform: translateY(100vh) translateX(0); opacity: 0; }
    10% { opacity: 1; }
    90% { opacity: 1; }
    100% { transform: translateY(-20vh) translateX(20px); opacity: 0; }
  }
  
  @keyframes floatUpSlow {
    0% { transform: translateY(100vh) translateX(0); opacity: 0; }
    10% { opacity: 0.6; }
    90% { opacity: 0.6; }
    100% { transform: translateY(-20vh) translateX(-15px); opacity: 0; }
  }
`;
if (typeof document !== 'undefined' && !document.getElementById('circuit-bg-animations')) {
  animationStyles.id = 'circuit-bg-animations';
  document.head.appendChild(animationStyles);
}

export const CircuitBackground: React.FC<CircuitBackgroundProps> = ({ color = 'purple' }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mousePos, setMousePos] = useState({ x: -1000, y: -1000 });
  const [particles, setParticles] = useState<InteractiveParticle[]>([]);
  const animationRef = useRef<number>();

  // 生成噪点纹理
  const noiseDataUrl = useMemo(() => {
    if (typeof document === 'undefined') return '';
    
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return '';
    
    canvas.width = 200;
    canvas.height = 200;
    
    const imageData = ctx.createImageData(200, 200);
    const data = imageData.data;
    
    for (let i = 0; i < data.length; i += 4) {
      const noise = Math.random() * 255;
      data[i] = noise;
      data[i + 1] = noise;
      data[i + 2] = noise;
      data[i + 3] = 8;
    }
    
    ctx.putImageData(imageData, 0, 0);
    return canvas.toDataURL();
  }, []);

  // 初始化交互粒子
  useEffect(() => {
    const initParticles: InteractiveParticle[] = Array.from({ length: 30 }, (_, i) => {
      const x = Math.random() * (typeof window !== 'undefined' ? window.innerWidth : 1920);
      const y = Math.random() * (typeof window !== 'undefined' ? window.innerHeight : 1080);
      return {
        id: i,
        x,
        y,
        baseX: x,
        baseY: y,
        size: 2 + Math.random() * 3,
        opacity: 0.3 + Math.random() * 0.4,
        speed: 0.5 + Math.random() * 1,
      };
    });
    setParticles(initParticles);
  }, []);

  // 鼠标移动追踪
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setMousePos({
          x: e.clientX - rect.left,
          y: e.clientY - rect.top,
        });
      }
    };

    const handleMouseLeave = () => {
      setMousePos({ x: -1000, y: -1000 });
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseleave', handleMouseLeave);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseleave', handleMouseLeave);
    };
  }, []);

  // 粒子动画循环
  useEffect(() => {
    const animate = () => {
      setParticles(prevParticles => 
        prevParticles.map(particle => {
          const dx = mousePos.x - particle.x;
          const dy = mousePos.y - particle.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          const maxDistance = 150;
          
          let newX = particle.x;
          let newY = particle.y;
          
          if (distance < maxDistance && distance > 0) {
            // 被鼠标推开
            const force = (maxDistance - distance) / maxDistance;
            const angle = Math.atan2(dy, dx);
            newX = particle.x - Math.cos(angle) * force * 8;
            newY = particle.y - Math.sin(angle) * force * 8;
          } else {
            // 缓慢回到基础位置
            newX = particle.x + (particle.baseX - particle.x) * 0.02;
            newY = particle.y + (particle.baseY - particle.y) * 0.02;
          }
          
          // 缓慢漂移基础位置
          const time = Date.now() * 0.001;
          const driftX = Math.sin(time * particle.speed + particle.id) * 0.3;
          const driftY = Math.cos(time * particle.speed * 0.7 + particle.id) * 0.3;
          
          return {
            ...particle,
            x: newX + driftX,
            y: newY + driftY,
          };
        })
      );
      animationRef.current = requestAnimationFrame(animate);
    };
    
    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [mousePos]);

  // 浮动粒子（非交互）
  const floatingParticles = useMemo(() => {
    return Array.from({ length: 8 }, (_, i) => ({
      id: i,
      left: `${5 + Math.random() * 90}%`,
      delay: `${Math.random() * 15}s`,
      duration: `${15 + Math.random() * 20}s`,
      size: 2 + Math.random() * 2,
      opacity: 0.3 + Math.random() * 0.3,
    }));
  }, []);

  return (
    <div ref={containerRef} className="absolute inset-0 overflow-hidden bg-[#0A0A0A] select-none pointer-events-none">
      {/* 矩形网格 */}
      <div 
        className="absolute inset-0 opacity-[0.15]"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: '50px 50px',
        }}
      />
      
      {/* 主渐变 - 带脉冲动画 */}
      <div 
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(
              ellipse 120% 80% at 50% 100%,
              rgba(255, 120, 50, 0.45) 0%,
              rgba(220, 80, 30, 0.35) 20%,
              rgba(150, 50, 20, 0.18) 40%,
              rgba(60, 20, 10, 0.08) 60%,
              transparent 80%
            )
          `,
          animation: 'gradientPulse 8s ease-in-out infinite',
        }}
      />
      
      {/* 次级渐变层 - 增加深度和暖色调 */}
      <div 
        className="absolute inset-0"
        style={{
          background: `
            radial-gradient(
              ellipse 100% 60% at 50% 110%,
              rgba(255, 100, 30, 0.5) 0%,
              rgba(200, 60, 20, 0.25) 30%,
              transparent 60%
            )
          `,
          animation: 'gradientPulse 12s ease-in-out infinite',
          animationDelay: '-4s',
        }}
      />
      
      {/* 交互粒子 - 被鼠标推开 */}
      {particles.map((particle) => (
        <div
          key={particle.id}
          className="absolute rounded-full bg-orange-400 transition-[width,height,opacity] duration-150"
          style={{
            left: particle.x,
            top: particle.y,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            opacity: particle.opacity,
            transform: 'translate(-50%, -50%)',
            boxShadow: '0 0 6px rgba(251, 146, 60, 0.5)',
          }}
        />
      ))}
      
      {/* 浮动粒子（上升） */}
      {floatingParticles.map((particle) => (
        <div
          key={`float-${particle.id}`}
          className="absolute rounded-full bg-orange-400"
          style={{
            left: particle.left,
            bottom: 0,
            width: `${particle.size}px`,
            height: `${particle.size}px`,
            opacity: particle.opacity,
            animation: `${particle.id % 2 === 0 ? 'floatUp' : 'floatUpSlow'} ${particle.duration} linear infinite`,
            animationDelay: particle.delay,
          }}
        />
      ))}
      
      {/* 顶部暗角渐变 */}
      <div 
        className="absolute inset-0"
        style={{
          background: `
            linear-gradient(
              to bottom,
              rgba(10, 10, 10, 0.8) 0%,
              transparent 40%
            )
          `,
        }}
      />
      
      {/* 噪点纹理层 - 降低透明度 */}
      {noiseDataUrl && (
        <div 
          className="absolute inset-0 opacity-[0.12]"
          style={{
            backgroundImage: `url(${noiseDataUrl})`,
            backgroundRepeat: 'repeat',
          }}
        />
      )}
      
      {/* 额外的细腻噪点层 (CSS 方式) - 降低透明度 */}
      <div 
        className="absolute inset-0 opacity-[0.08]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 400 400' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
        }}
      />
    </div>
  );
};

