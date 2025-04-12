import discord
from discord.ext import commands
from discord import app_commands

class TestCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="test_slash", description="Commande test simple.")
    async def test_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message("✅ Slash command test fonctionnelle !", ephemeral=True)

# 🔧 Fonction de setup standard obligatoire pour que le Cog se charge
async def setup(bot):
    await bot.add_cog(TestCommands(bot))
