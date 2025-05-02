import discord
from discord.ext import commands
from utils.utils import load_reaction_role_mapping, log_erreur

class ReactionRoleEvents(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        try:
            if payload.member is None or payload.member.bot:
                return

            mapping = load_reaction_role_mapping()
            role_infos = mapping.get(str(payload.message_id))
            if not role_infos:
                return

            for entry in role_infos:
                if entry["emoji"] == str(payload.emoji):
                    guild = self.bot.get_guild(payload.guild_id)
                    role = guild.get_role(int(entry["role_id"]))
                    if role:
                        member = payload.member
                        if role not in member.roles:
                            await member.add_roles(role)
        except Exception as e:
            guild = self.bot.get_guild(payload.guild_id)
            await log_erreur(self.bot, guild, f"Erreur on_raw_reaction_add : {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        try:
            mapping = load_reaction_role_mapping()
            role_infos = mapping.get(str(payload.message_id))
            if not role_infos:
                return

            for entry in role_infos:
                if entry["emoji"] == str(payload.emoji):
                    guild = self.bot.get_guild(payload.guild_id)
                    role = guild.get_role(int(entry["role_id"]))
                    if not role:
                        continue
                    member = await guild.fetch_member(payload.user_id)  # Correction ici
                    if role in member.roles:
                        await member.remove_roles(role)
        except Exception as e:
            guild = self.bot.get_guild(payload.guild_id)
            await log_erreur(self.bot, guild, f"Erreur on_raw_reaction_remove : {e}")

async def setup(bot):
    await bot.add_cog(ReactionRoleEvents(bot))
