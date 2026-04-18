"""
Voice Agent — the main orchestrator tying together:
  - Voice input (microphone + VAD)
  - On-device inference (Cactus + Gemma 4)
  - Cloud fallback (Gemini)
  - Tool execution (function calling)
  - Voice output (TTS placeholder)

Run as:
    python -m src.agent
"""

import json
import logging
import sys
from typing import Optional

from src.config import cfg
from src.cactus_engine import CactusEngine
from src.cloud_fallback import CloudFallback
from src.voice_handler import VoiceHandler
from src.tools import get_tools_json, handle_function_calls

# ── Logging Setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class VoiceAgent:
    """
    Main voice agent class.

    Orchestrates the full pipeline:
      mic → (VAD) → Gemma 4 on Cactus → (tools / cloud fallback) → response
    """

    def __init__(self):
        self.engine = CactusEngine()
        self.voice = VoiceHandler()
        self.cloud = CloudFallback()
        self.conversation_history: list[dict] = []
        self.system_prompt = (
            "You are a helpful voice assistant powered by Gemma 4. "
            "You run entirely on-device for fast, private responses. "
            "Be concise — your responses will be spoken aloud."
        )

    def initialize(self) -> bool:
        """Initialize all subsystems."""
        logger.info("=" * 60)
        logger.info("🌵 Cactus x DeepMind Voice Agent")
        logger.info("=" * 60)

        # Validate config
        issues = cfg.validate()
        if issues:
            for issue in issues:
                logger.warning(f"⚠️  {issue}")

        logger.info(f"Config: {cfg}")

        # Initialize Cactus engine
        if self.engine.is_available:
            self.engine.initialize()
            self.engine.initialize_transcription()
            return True
        else:
            logger.error(
                "❌ Cactus SDK not available. Please run:\n"
                "   ./scripts/setup_cactus.sh"
            )
            return False

    def process_text(self, user_input: str) -> str:
        """
        Process a text input through the full pipeline.

        Returns the assistant's response text.
        """
        logger.info(f"👤 User: {user_input}")

        # Step 1: On-device completion with tool support
        result = self.engine.complete(
            user_message=user_input,
            system_prompt=self.system_prompt,
            tools_json=get_tools_json(),
            on_token=lambda token, _: print(token, end="", flush=True),
        )

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            logger.error(f"❌ Engine error: {error}")
            return f"Sorry, I encountered an error: {error}"

        # Step 2: Handle function calls if any
        function_calls = result.get("function_calls", [])
        if function_calls:
            tool_results = handle_function_calls(function_calls)
            # TODO: Feed tool results back into the model for a follow-up response
            logger.info(f"🔧 Tool results: {tool_results}")

        # Step 3: Check if cloud fallback is needed
        if cfg.ENABLE_CLOUD_FALLBACK and self.cloud.should_fallback(result):
            logger.info("☁️ Routing to cloud…")
            cloud_response = self.cloud.query(user_input, self.system_prompt)
            if cloud_response:
                return cloud_response

        response = result.get("response", "")
        logger.info(f"🤖 Assistant: {response}")
        return response

    def process_voice(self) -> str:
        """
        Record voice → process on-device → return response.

        Uses Gemma 4's native audio understanding for single-pass processing.
        """
        if not self.voice.is_available:
            return "Audio not available. Please install sounddevice."

        # Record until user stops speaking
        audio = self.voice.record_until_silence()

        # Option A: Native multimodal (Gemma 4 processes audio directly)
        pcm_data = VoiceHandler.audio_to_pcm_list(audio)
        result = self.engine.complete_with_audio(
            pcm_data=pcm_data,
            system_prompt=self.system_prompt,
            tools_json=get_tools_json(),
        )

        if result.get("success"):
            response = result.get("response", "")
            logger.info(f"🤖 Assistant: {response}")
            return response

        return "Sorry, I couldn't process that audio."

    def run_interactive(self) -> None:
        """
        Run the agent in interactive text mode (for development/testing).

        Type messages to chat. Commands:
          /voice  — switch to voice input for one turn
          /quit   — exit
          /reset  — clear conversation history
        """
        print("\n🌵 Voice Agent ready! Type a message or /voice for mic input.\n")

        while True:
            try:
                user_input = input("You: ").strip()

                if not user_input:
                    continue
                elif user_input == "/quit":
                    print("👋 Goodbye!")
                    break
                elif user_input == "/reset":
                    self.engine.reset()
                    self.conversation_history.clear()
                    print("🔄 Conversation reset.\n")
                    continue
                elif user_input == "/voice":
                    response = self.process_voice()
                else:
                    response = self.process_text(user_input)

                print(f"\nAssistant: {response}\n")

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break

    def shutdown(self) -> None:
        """Clean up all resources."""
        self.engine.shutdown()
        logger.info("👋 Agent shut down.")


# ── Entry Point ───────────────────────────────────────────────

def main():
    agent = VoiceAgent()

    if not agent.initialize():
        logger.error("Failed to initialize. Exiting.")
        sys.exit(1)

    try:
        agent.run_interactive()
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()
