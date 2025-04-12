import discord
from discord.ext import commands
import json
import os
from utils.utils import log_erreur

WHITELIST_PATH = "data/whitelist.json"

def charger_whitelist():
    if not os.path.exists(WHITELIST_PATH):
        return []
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_whitelist(whitelist):
    os.makedirs("data", exist_ok=True)
    with open(WHITELIST_PATH, "w", encoding="utf-8") as f:
        json.dump(whitelist, f, indent=4)

class WhitelistEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            whitelist = charger_whitelist()
            role_membre = discord.utils.get(member.guild.roles, name="Membre")
            role_non_verifie = discord.utils.get(member.guild.roles, name="Non vérifié")

            if member.id in whitelist:
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
