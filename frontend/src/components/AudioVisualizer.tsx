import { motion } from "framer-motion";

export const AudioVisualizer = () => {
  // Use deterministic math to generate "random" values based on index
  // This avoids hydration mismatches while creating a chaotic/random appearance
  const bars = Array.from({ length: 29 }, (_, i) => {
    // Generate different height patterns for each bar
    const h1 = 20 + Math.abs(Math.sin(i * 12.34) * 30); // 20-50%
    const h2 = 50 + Math.abs(Math.cos(i * 23.45) * 40); // 50-90%
    const h3 = 30 + Math.abs(Math.sin(i * 34.56) * 40); // 30-70%
    const h4 = 60 + Math.abs(Math.cos(i * 45.67) * 30); // 60-90%

    // Vary the duration significantly to prevent them from syncing up
    // Range: ~1.5s to ~3.0s (slowed down as requested)
    const duration = 1.8 + Math.abs(Math.sin(i * 100)) * 1.5;

    // Stagger delays to start at different times
    const delay = Math.abs(Math.cos(i * 50)) * 0.5;

    return {
      id: i,
      // More keyframes for more complex movement
      heights: [`${h1}%`, `${h2}%`, `${h3}%`, `${h4}%`, `${h2}%`, `${h1}%`],
      duration,
      delay,
    };
  });

  return (
    <div className="flex items-center justify-center h-48 gap-1 bg-white p-6 rounded-2xl">
      {bars.map((bar) => (
        <motion.div
          key={bar.id}
          className="w-1.5 rounded-full"
          animate={{
            height: bar.heights,
          }}
          transition={{
            duration: bar.duration,
            repeat: Infinity,
            repeatType: "mirror",
            delay: bar.delay,
            ease: "easeInOut",
          }}
          style={{
            height: "20%", // Initial height
            background: "linear-gradient(to bottom, #EBA9A1, #AC82A9)",
          }}
        />
      ))}
    </div>
  );
};
