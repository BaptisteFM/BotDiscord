import discord
from discord.ext import commands
import json
import os
from utils.utils import log_erreur, charger_config

WHITELIST_PATH = "/data/whitelist.json"

def charger_whitelist():
    if not os.path.exists(WHITELIST_PATH):
        return []
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_whitelist(whitelist):
    os.makedirs(os.path.dirname(WHITELIST_PATH), exist_ok=True)
    with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
        json.dump(whitelist, f, indent=4)

class WhitelistEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            whitelist = charger_whitelist()
            whitelist_ids = [entry.get("user_id") for entry in whitelist]

            config = charger_config()
            role_membre = member.guild.get_role(int(config.get("role_membre_id", 0)))
            role_non_verifie = member.guild.get_role(int(config.get("role_non_verifie_id", 0)))

            if member.id in whitelist_ids:
                if role_membre:
                    await member.add_roles(role_membre)
                    try:
                        await member.send("✅ Tu as été automatiquement intégré au serveur. Bienvenue !")
                    except:
                        pass
            else:
                if role_non_verifie:
                    await member.add_roles(role_non_verifie)

        except Exception as e:
            await log_erreur(self.bot, member.guild, f"on_member_join : {e}")

async def setup(bot):
    await bot.add_cog(WhitelistEvents(bot))
