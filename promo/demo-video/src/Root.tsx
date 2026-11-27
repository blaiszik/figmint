import { Composition } from "remotion";
import { MintCheck, DURATION, FPS } from "./Video";
import { AgentReply, AGENT_DURATION, AGENT_FPS } from "./AgentVideo";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="MintCheck" component={MintCheck} durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
    <Composition id="MintCheckSquare" component={MintCheck} durationInFrames={DURATION} fps={FPS} width={1080} height={1080} />
    <Composition id="AgentReply" component={AgentReply} durationInFrames={AGENT_DURATION} fps={AGENT_FPS} width={1920} height={1080} />
    <Composition id="AgentReplySquare" component={AgentReply} durationInFrames={AGENT_DURATION} fps={AGENT_FPS} width={1080} height={1080} />
  </>
);
