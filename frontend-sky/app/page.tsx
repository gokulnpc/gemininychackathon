import Navbar from "@/components/navbar"
import HeroSection from "@/components/hero-section"
import ContentCardsSection from "@/components/content-cards-section"
import HowItWorksSection from "@/components/how-it-works-section"
import CTASection from "@/components/cta-section"
import FooterSection from "@/components/footer-section"

export default function Home() {
  return (
    <main>
      <Navbar />
      <HeroSection />
      <ContentCardsSection />
      <HowItWorksSection />
      <CTASection />
      <FooterSection />
    </main>
  )
}
