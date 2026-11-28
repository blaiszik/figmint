import { Composition } from "remotion";
import { MintCheck, DURATION, FPS } from "./Video";
import { AgentReply, AGENT_DURATION, AGENT_FPS } from "./AgentVideo";
import { BrailleShowcase, BRAILLE_DURATION, BRAILLE_FPS, BRAILLE_SECONDS } from "./BrailleVideo";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="MintCheck" component={MintCheck} durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="MintCheckSquare" component={MintCheck} durationInFrames={DURATION} fps={FPS} width={1080} height={1080} />
    <Composition id="AgentReply" component={AgentReply} durationInFrames={AGENT_DURATION} fps={AGENT_FPS} width={1920} height={1080} />
    <Composition id="AgentReplySquare" component={AgentReply} durationInFrames={AGENT_DURATION} fps={AGENT_FPS} width={1080} height={1080} />
    <Composition id="BrailleShowcase" component={BrailleShowcase} durationInFrames={BRAILLE_DURATION} fps={BRAILLE_FPS} width={1920} height={1080} defaultProps={{ flatBg: false }} />
    <Composition id="BrailleShowcaseSquare" component={BrailleShowcase} durationInFrames={BRAILLE_DURATION} fps={BRAILLE_FPS} width={1080} height={1080} defaultProps={{ flatBg: false }} />
    <Composition id="BrailleShowcaseGif" component={BrailleShowcase} durationInFrames={Math.round(BRAILLE_SECONDS * 12)} fps={12} width={1280} height={720} defaultProps={{ flatBg: true }} />
  </>
);
