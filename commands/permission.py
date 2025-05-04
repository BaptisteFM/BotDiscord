# commands/permission.py
import discord
from discord import app_commands
from discord.ext import commands
from utils.utils import charger_permissions

class PermissionFilter(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # On garde le check pour sécuriser l'invocation même en DM
        bot.tree.add_check(self.global_permission_check)

    async def global_permission_check(self, interaction: discord.Interaction) -> bool:
        # 1) Charge la config
        permissions_config = charger_permissions()

        # 2) Cherche d'abord par nom de commande
        key = interaction.command.name
        allowed = permissions_config.get(key)

        # 3) Fallback sur catégorie
        if allowed is None:
            cat = getattr(interaction.command, "category", None)
            allowed = permissions_config.get(cat, [])

        # 4) Vérifie user ou roles
        uid = str(interaction.user.id)
        roles = {str(r.id) for r in interaction.user.roles}
        if uid in allowed or roles.intersection(allowed):
            return True

        # 5) Sinon, lève pour empêcher invocation (et cacher en DM)
        raise app_commands.CheckFailure()

async def setup_permission_filter(bot: commands.Bot):
    await bot.add_cog(PermissionFilter(bot))
