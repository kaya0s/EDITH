"""
utils/user_profile.py
=====================
User profile management for Jarvis AI Platform.

Handles user name storage and retrieval for personalized interactions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from config.settings import BASE_DIR, EXIT_PHRASES
from utils import ui

logger = logging.getLogger(__name__)

# User profile file path
PROFILE_FILE = BASE_DIR / "user_profile.json"


class UserProfile:
    """Manages user profile data including name and preferences."""
    
    def __init__(self) -> None:
        self._name: Optional[str] = None
        self._profile_data: dict = {}
        self._load_profile()
    
    def _load_profile(self) -> None:
        """Load user profile from file or create default."""
        try:
            if PROFILE_FILE.exists():
                with open(PROFILE_FILE, 'r', encoding='utf-8') as f:
                    self._profile_data = json.load(f)
                self._name = self._profile_data.get('name')
                logger.info(f"Loaded profile for user: {self._name}")
            else:
                self._profile_data = {}
                self._name = None
                logger.info("No existing profile found")
        except Exception as exc:
            logger.error(f"Failed to load user profile: {exc}")
            self._profile_data = {}
            self._name = None
    
    def _save_profile(self) -> None:
        """Save user profile to file."""
        try:
            # Ensure the profile data is current
            if self._name:
                self._profile_data['name'] = self._name
            
            with open(PROFILE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._profile_data, f, indent=2)
            logger.info(f"Saved profile for user: {self._name}")
        except Exception as exc:
            logger.error(f"Failed to save user profile: {exc}")
    
    def get_name(self) -> Optional[str]:
        """Get the user's name."""
        return self._name
    
    def set_name(self, name: str) -> None:
        """Set the user's name and save to profile."""
        self._name = name.strip()
        self._profile_data['name'] = self._name
        self._save_profile()
        logger.info(f"Updated user name to: {self._name}")
    
    def has_name(self) -> bool:
        """Check if user has a name set."""
        return bool(self._name and self._name.strip())
    
    def _is_valid_name(self, name: str) -> tuple[bool, str]:
        """
        Validate user name for appropriateness and conflicts.
        
        Returns:
            tuple: (is_valid, error_message)
        """
        name_lower = name.lower().strip()
        
        # Check for exit phrases
        for exit_phrase in EXIT_PHRASES:
            if exit_phrase.lower() in name_lower:
                return False, "This name contains a command word. Please choose a different name."
        
        # Check for common inappropriate words (basic filter)
        inappropriate_words = {
            'admin', 'administrator', 'root', 'system', 'guest', 'user',
            'test', 'demo', 'sample', 'example', 'null', 'undefined',
            'fuck', 'shit', 'damn', 'hell', 'bitch', 'bastard',
            'ass', 'asshole', 'dick', 'pussy', 'cock', 'cunt'
        }
        
        # Check if name is exactly an inappropriate word
        if name_lower in inappropriate_words:
            return False, "This name is not appropriate. Please choose a different name."
        
        # Check if name contains inappropriate words
        for word in inappropriate_words:
            if word in name_lower and len(word) > 2:  # Only check words longer than 2 chars
                return False, "This name contains inappropriate words. Please choose a different name."
        
        # Check for only numbers or special characters
        if not any(c.isalpha() for c in name):
            return False, "Name must contain at least one letter."
        
        # Check for repeated characters (like "aaa")
        if len(set(name.lower())) < 2 and len(name) > 2:
            return False, "Name cannot be just repeated characters."
        
        return True, ""
    
    def prompt_for_name(self) -> str:
        """
        Prompt user for their name if not already set.
        Returns the user's name.
        """
        if self.has_name():
            return self._name
        
        # Use chat UI style for setup (no divider for cleaner setup experience)
        ui.print_jarvis_stream("Welcome to Jarvis! Let's get you set up. What's your name?", char_delay=0.02)
        
        while True:
            try:
                name_input = ui.get_user_input()
                if not name_input or not name_input.strip():
                    ui.print_jarvis_stream("Please enter a name.", char_delay=0.02)
                    continue
                
                name = name_input.strip()
                if len(name) < 2:
                    ui.print_jarvis_stream("Name should be at least 2 characters.", char_delay=0.02)
                    continue
                
                if len(name) > 50:
                    ui.print_jarvis_stream("Name is too long (max 50 characters).", char_delay=0.02)
                    continue
                
                # Validate name for appropriateness
                is_valid, error_msg = self._is_valid_name(name)
                if not is_valid:
                    ui.print_jarvis_stream(error_msg, char_delay=0.02)
                    continue
                
                # Valid name received - show boot info and start fresh chat
                self.set_name(name)
                # Show boot info with personalized welcome
                self._show_boot_info_after_setup()
                return name
                
            except (EOFError, KeyboardInterrupt):
                self.set_name("User")
                # Show boot info with default user
                self._show_boot_info_after_setup()
                return "User"
    
    def _show_boot_info_after_setup(self) -> None:
        """
        Show boot info after setup is complete with appropriate welcome message.
        """
        try:
            from config.settings import EXIT_PHRASES, INTERACTION_MODE
            # Use "Welcome to Jarvis!" for first-time setup, "Welcome back" for configured users
            welcome_msg = "Welcome to Jarvis!" if self.get_name() == "User" else f"Welcome back, {self.get_name()}!"
            import os

            ui_layout = os.getenv("JARVIS_UI_LAYOUT", "full").lower().strip()
            ui.hard_clear_screen()
            if ui_layout == "full":
                ui.display_header(github_url="github.com/kaya0s/J.git")
                ui.print_boot_info(
                    modules=[INTERACTION_MODE.lower().strip()],
                    exit_phrases=EXIT_PHRASES,
                    interaction_mode=INTERACTION_MODE,
                    welcome_message=welcome_msg,
                )
            else:
                ui.print_status_bar(
                    modules=[INTERACTION_MODE.lower().strip()],
                    exit_phrases=EXIT_PHRASES,
                    interaction_mode=INTERACTION_MODE,
                    welcome_message=welcome_msg,
                )
        except Exception as exc:
            logger.warning(f"Failed to show boot info after setup: {exc}")
    
    def get_personalized_prompt(self, base_prompt: str) -> str:
        """
        Return the base prompt without name personalization.
        Jarvis will address the user as 'Sir' per the system prompt.
        """
        return base_prompt


# Global profile instance
_user_profile: Optional[UserProfile] = None


def get_user_profile() -> UserProfile:
    """Get the global user profile instance."""
    global _user_profile
    if _user_profile is None:
        _user_profile = UserProfile()
    return _user_profile


def initialize_user_profile() -> str:
    """
    Initialize user profile and prompt for name if needed.
    Returns the user's name.
    """
    profile = get_user_profile()
    return profile.prompt_for_name()
