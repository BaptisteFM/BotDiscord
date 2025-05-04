# main.py
import discord
from discord.ext import commands
import asyncio
import os
import json
from dotenv import load_dotenv
from keep_alive import keep_alive
from utils.utils import charger_config, charger_permissions, PERMISSIONS_PATH
from discord import app_commands

# ─── Création du dossier /data si nécessaire ───────────────────
os.makedirs("/data", exist_ok=True)

# ─── Création du fichier permissions.json vide s’il n’existe pas ─
if not os.path.exists(PERMISSIONS_PATH):
    with open(PERMISSIONS_PATH, "w", encoding="utf-8") as f:
        json.dump({}, f, indent=4)

# ─── Lancement du serveur keep-alive ────────────────────────────
keep_alive()

# ─── Chargement des variables d’environnement ──────────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ─── Définition des intents ────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Chargement de tous les Cogs
        from commands.admin import setup_admin_commands
        from commands.utilisateur import setup_user_commands
        from commands.support import setup_support_commands
        from commands.test_command import setup as setup_test
        from commands.events import setup as setup_events
        from commands import whitelist, loisir, missions, reaction_roles, checkin

        await setup_test(self)
        await setup_admin_commands(self)
        await setup_user_commands(self)
        await setup_support_commands(self)
        await setup_events(self)
        await whitelist.setup(self)
        await loisir.setup(self)
        await missions.setup(self)
        await reaction_roles.setup(self)
        await checkin.setup(self)

    async def on_ready(self):
        print(f"✅ Connecté en tant que {self.user} (ID : {self.user.id})")
        try:
            synced = await self.tree.sync()
            print(f"✅ {len(synced)} commandes synchronisées.")
        except Exception as e:
            print(f"❌ Erreur lors de la synchronisation : {e}")
        # Application des permissions après la synchronisation
        await self.apply_command_permissions()

    async def apply_command_permissions(self):
        """
        Pour chaque guild et chaque slash command :
        1) on masque toujours la commande (permissions = none)
        2) on recharge permissions.json
        3) on applique les overrides pour les rôles/membres autorisés
        """
        permissions_config = charger_permissions()  # { "commande": [id,...], "categorie": [id,...] }

        for guild in self.guilds:
            for command in self.tree.get_commands(guild=guild):
                # ➊ Masquer la commande pour tout le monde
                await command.edit(
                    guild=guild,
                    default_member_permissions=0,  # aucun droit
                    dm_permission=False
                )

                # ➋ Récupérer la liste d'IDs autorisés (rôles ou membres)
                allowed = permissions_config.get(command.name)
                if allowed is None:
                    # fallback sur la catégorie si définie dans le Cog
                    cat = getattr(command, "category", None)
                    allowed = permissions_config.get(cat, [])

                # ➌ Si on a des IDs autorisés, on prépare les overrides
                if allowed:
                    perms = []
                    for id_str in allowed:
                        id_int = int(id_str)
                        if guild.get_role(id_int) is not None:
                            # c'est un rôle
                            perms.append(app_commands.AppCommandPermission(
                                id=id_int,
                                type=app_commands.AppCommandPermissionType.role,
                                permission=True
                            ))
                        else:
                            # on suppose que c'est un user ID
                            perms.append(app_commands.AppCommandPermission(
                                id=id_int,
                                type=app_commands.AppCommandPermissionType.user,
                                permission=True
                            ))
                    # ➍ Appliquer les overrides
                    await self.tree.set_permissions(command, guild=guild, permissions=perms)

# ─── Instanciation et lancement du bot ─────────────────────────
bot = MyBot()

if __name__ == "__main__":
    asyncio.run(bot.start(TOKEN))
