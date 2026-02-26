import type {
  VoiceData,
  MusicData,
  ArtStyle,
  CaptionStyle,
  EffectData,
  Scene,
  ProcessStep,
} from "@/types";

export const formats = [
  "Storytelling",
  "What if",
  "5 things you didn't know",
  "Random fact",
];

export const presets = [
  {
    id: "scary-stories",
    title: "Scary stories",
    description: "Scary stories that give you goosebumps",
  },
  {
    id: "history",
    title: "History",
    description:
      "Viral videos about history spanning from ancient times to the modern day",
  },
  {
    id: "true-crime",
    title: "True Crime",
    description: "Viral videos about true crime stories",
  },
  {
    id: "stoic-motivation",
    title: "Stoic Motivation",
    description: "Viral videos about stoic philosophy and life lessons",
  },
  {
    id: "marketing-business",
    title: "Marketing & Business",
    description: "Product launches, business tips, and growth strategies",
  },
  {
    id: "tech-innovation",
    title: "Tech & Innovation",
    description: "Latest tech news, gadget reviews, and innovations",
  },
];

export const voices: VoiceData[] = [
  {
    id: "your-own",
    name: "Your Own",
    gender: "Me",
    description: "Clone your own voice",
    avatarColor: "linear-gradient(135deg, #D4A5B5 0%, #A88BA8 100%)",
  },
  {
    id: "adam",
    name: "Adam",
    gender: "Male",
    description: "The well-known voice of tiktok and Instagram",
    avatarColor: "linear-gradient(135deg, #A8D8EA 0%, #7FB3D5 100%)",
  },
  {
    id: "john",
    name: "John",
    gender: "Male",
    description: "The perfect storyteller, very realistic and natural",
    avatarColor: "linear-gradient(135deg, #F4A261 0%, #E76F51 100%)",
  },
  {
    id: "emma",
    name: "Emma",
    gender: "Female",
    description: "Professional and clear, great for educational content",
    avatarColor: "linear-gradient(135deg, #C9A9B8 0%, #B08D9F 100%)",
  },
  {
    id: "sarah",
    name: "Sarah",
    gender: "Female",
    description: "Warm and engaging, perfect for lifestyle content",
    avatarColor: "linear-gradient(135deg, #E9C46A 0%, #F4A261 100%)",
  },
];

export const musicTracks: MusicData[] = [
  {
    id: "happy-rhythm",
    title: "Happy rhythm",
    description: "Upbeat and energetic, perfect for positive content",
    iconColor: "#F4A5B5",
    audioFile: "/music/happy_rhythm.mp3",
  },
  {
    id: "quiet-before-storm",
    title: "Quiet before storm",
    description: "Building tension and anticipation for dramatic reveals",
    iconColor: "#A88BA8",
    audioFile: "/music/quiet_before_storm.mp3",
  },
  {
    id: "peaceful-vibes",
    title: "Peaceful vibes",
    description: "Calm and soothing background for relaxed storytelling",
    iconColor: "#A8D8D8",
    audioFile: "/music/peaceful_vibes.mp3",
  },
  {
    id: "brilliant-symphony",
    title: "Brilliant symphony",
    description: "Orchestral and melodic for epic storytelling",
    iconColor: "#B8A8D8",
    audioFile: "/music/brilliant_symphony.mp3",
  },
  {
    id: "breathing-shadows",
    title: "Breathing shadows",
    description: "Mysterious and eerie ambiance for suspenseful videos",
    iconColor: "#9A8AA8",
    audioFile: "/music/breathing_shadows.mp3",
  },
];

export const artStyles: ArtStyle[] = [
  {
    id: "realism",
    name: "Realism",
    description: "Hyper-realistic photographic imagery",
  },
  {
    id: "comic",
    name: "Comic",
    description: "Illustrated comic book style with vibrant colors",
  },
  {
    id: "creepy-comic",
    name: "Creepy Comic",
    description: "Dark, gritty comic style for horror and suspense",
  },
  {
    id: "painting",
    name: "Painting",
    description: "Painterly artwork with rich textures and brushstrokes",
  },
  {
    id: "ghibli",
    name: "Ghibli",
    description: "Dreamy, nature-inspired Studio Ghibli-like aesthetic",
  },
  {
    id: "disney",
    name: "Disney",
    description: "Bright and expressive Disney-inspired animation style",
  },
  {
    id: "polaroid",
    name: "Polaroid",
    description: "Nostalgic polaroid photo style with soft warm tones",
  },
];

export const captionStyles: CaptionStyle[] = [
  { id: "bold-stroke", name: "Bold Stroke", preview: "THE" },
  { id: "red-highlight", name: "Red Highlight", preview: "ON THE" },
  { id: "sleek", name: "Sleek", preview: "ON THE" },
  { id: "karaoke", name: "Karaoke", preview: "ON THE" },
  { id: "majestic", name: "Majestic", preview: "ON THE" },
  { id: "beast", name: "Beast", preview: "THE" },
  { id: "elegant", name: "Elegant", preview: "THE" },
  { id: "clarity", name: "Clarity", preview: "the" },
];

export const effects: EffectData[] = [
  {
    id: "shake-effect",
    name: "Shake effect",
    description:
      "Subjects pop out with subtle motion — great for horror, thriller, and suspenseful stories.",
    tag: "NEW",
  },
  {
    id: "film-grain",
    name: "Film grain",
    description:
      "Add an old film look with scanthes, dust particles, noise, and a subtle vigetta.",
    tag: "NEW",
  },
  {
    id: "animated-stock",
    name: "Animated stock",
    description:
      "Generate a 5-second motion video for the first scene to hook viewers instantly.",
    tag: "PREMIUM",
  },
];

export const scenes: Scene[] = [
  {
    id: 1,
    title: "Hook",
    description: "Are you tired of spending hours on video editing?",
    timestamp: "0:00",
  },
  {
    id: 2,
    title: "Problem",
    description: "Traditional video creation is time-consuming and expensive",
    timestamp: "0:15",
  },
  {
    id: 3,
    title: "Solution",
    description: "Introducing VoiceVidAI - voice to video in 60 seconds",
    timestamp: "0:30",
  },
  {
    id: 4,
    title: "CTA",
    description: "Try it free today and transform your content creation",
    timestamp: "0:45",
  },
];

export const processingSteps: ProcessStep[] = [
  {
    id: 1,
    title: "Understanding Your Input",
    description: "Converting speech to text with emotion detection",
  },
  {
    id: 2,
    title: "Crafting Your Story",
    description: "Generating script with hooks and call-to-action",
  },
  {
    id: 3,
    title: "Finding Perfect Visuals",
    description: "Semantic search across thousands of assets",
  },
  {
    id: 4,
    title: "Composing Your Video",
    description: "Assembling final video at 1080p",
  },
];

export const sidebarItems = [
  { id: 1, label: "Your Message", icon: "Mic" },
  { id: 2, label: "Language & Voice", icon: "Volume2" },
  { id: 3, label: "Background Music", icon: "Music" },
  { id: 4, label: "Art Style", icon: "Palette" },
  { id: 5, label: "Caption Style", icon: "Type" },
  { id: 6, label: "Effects", icon: "Zap" },
  { id: 7, label: "Video Details", icon: "Clock" },
  { id: 8, label: "Review Outputs", icon: "Eye" },
];

export const stepTitles: Record<number, { title: string; subtitle: string }> = {
  1: {
    title: "Create Your Message",
    subtitle: "Customize every aspect of your video with our AI-powered tools",
  },
  2: {
    title: "Language & Voice",
    subtitle: "Choose the language and voice style for your video",
  },
  3: {
    title: "Background Music",
    subtitle:
      "Choose as many songs as you want, we'll pick a random one for each video",
  },
  4: { title: "Art Style", subtitle: "Choose the visual style for your video" },
  5: {
    title: "Caption Style",
    subtitle: "Choose the visual style for your video",
  },
  6: {
    title: "Effects",
    subtitle:
      "Add visual effects to make your videos more engaging and eye-catching",
  },
  7: {
    title: "Video Details",
    subtitle: "Finalize your Video Details and posting schedule",
  },
  8: {
    title: "Review Your Video",
    subtitle: "",
  },
};
