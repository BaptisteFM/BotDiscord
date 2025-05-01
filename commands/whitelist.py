import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime
from utils.utils import (
    is_admin,
    is_non_verified_user,
    charger_config,
    sauvegarder_config,
    log_erreur,
    role_autorise
)

# Chemin du fichier stockant les demandes en attente
DEMANDES_PATH = "data/demandes_whitelist.json"

def _charger_demandes():
    if not os.path.exists(DEMANDES_PATH):
        return []
    try:
        with open(DEMANDES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def _sauvegarder_demandes(data):
    os.makedirs("data", exist_ok=True)
    with open(DEMANDES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

class Whitelist(commands.Cog, name="whitelist"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # boucle de polling réaction toutes les 15s
        self.check_reactions.start()
        # boucle de rappel demande toutes les heures
        self.rappel_demande.start()

    # — Helpers JSON —
    async def charger_demandes(self):
        return await self.bot.loop.run_in_executor(None, _charger_demandes)

    async def sauvegarder_demandes(self, data):
        await self.bot.loop.run_in_executor(None, lambda: _sauvegarder_demandes(data))

    async def ajouter_demande(self, user_id: int, timestamp: str, nom: str, prenom: str):
        demandes = await self.charger_demandes()
        for d in demandes:
            if d["user_id"] == str(user_id):
                d.update({"timestamp": timestamp, "nom": nom, "prenom": prenom})
                break
        else:
            demandes.append({
                "user_id": str(user_id),
                "timestamp": timestamp,
                "nom": nom,
                "prenom": prenom
            })
        await self.sauvegarder_demandes(demandes)

    async def supprimer_demande(self, user_id: int):
        demandes = await self.charger_demandes()
        restantes = [d for d in demandes if d["user_id"] != str(user_id)]
        await self.sauvegarder_demandes(restantes)

    # — Commande admin : publier le message réactionnel —
    @app_commands.command(
        name="afficher_demande_acces",
        description="Publie le message pour demander l'accès par réaction ✅"
    )
    @app_commands.default_permissions(administrator=True)
    async def afficher_demande_acces(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)

        embed = discord.Embed(
            title="📥 Demande d'accès",
            description="Réagissez avec ✅ pour demander l'accès au serveur.",
            color=discord.Color.blue()
        )
        msg = await interaction.channel.send(embed=embed)
        await msg.add_reaction("✅")

        cfg = charger_config()
        cfg["demande_acces_channel_id"] = str(interaction.channel.id)
        cfg["demande_acces_message_id"]   = str(msg.id)
        sauvegarder_config(cfg)

        await interaction.response.send_message("✅ Message d'accès publié.", ephemeral=True)

    # — Polling : vérifier les réactions régulièrement —
    @tasks.loop(seconds=15)
    async def check_reactions(self):
        try:
            cfg = charger_config()
            chan_id = int(cfg.get("demande_acces_channel_id", 0))
            msg_id  = int(cfg.get("demande_acces_message_id", 0))
            if not chan_id or not msg_id:
                return

            channel = self.bot.get_channel(chan_id)
            if not channel:
                return
            message = await channel.fetch_message(msg_id)

            # repérer la réaction ✅
            reaction = discord.utils.get(message.reactions, emoji="✅")
            if not reaction or reaction.count < 1:
                return

            users = await reaction.users().flatten()
            for user in users:
                if user.id == self.bot.user.id:
                    continue
                if not await is_non_verified_user(user):
                    continue

                # éviter re-traiter la même demande : voir dans demands.json
                demandes = await self.charger_demandes()
                if any(d["user_id"] == str(user.id) for d in demandes):
                    # supprimer quand même la réaction
                    try: await message.remove_reaction("✅", user)
                    except: pass
                    continue

                # on supprime la réaction pour éviter le spam
                try:
                    await message.remove_reaction("✅", user)
                except:
                    pass

                # DM pour nom / prénom
                try:
                    dm = await user.create_dm()
                    await dm.send("📝 **Demande d'accès**\nQuel est votre **nom** ?")
                    def check_name(m: discord.Message):
                        return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)
                    name_msg = await self.bot.wait_for('message', check=check_name, timeout=300)

                    await dm.send("📝 Merci ! Quel est votre **prénom** ?")
                    def check_prenom(m: discord.Message):
                        return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)
                    prenom_msg = await self.bot.wait_for('message', check=check_prenom, timeout=300)

                    # enregistrement de la demande
                    await self.ajouter_demande(
                        user_id=user.id,
                        timestamp=datetime.utcnow().isoformat(),
                        nom=name_msg.content.strip(),
                        prenom=prenom_msg.content.strip()
                    )
                    await dm.send("✅ Votre demande a été transmise aux modérateurs.")

                    # notification staff
                    embed = discord.Embed(
                        title="📨 Nouvelle demande d'accès",
                        description=(
                            f"<@{user.id}> a demandé à rejoindre le serveur.\n"
                            f"**Nom** : {name_msg.content}\n"
                            f"**Prénom** : {prenom_msg.content}"
                        ),
                        color=discord.Color.blurple()
                    )
                    embed.set_footer(text=f"ID utilisateur : {user.id}")
                    val_chan_id = cfg.get("journal_validation_channel")
                    if val_chan_id:
                        val_chan = channel.guild.get_channel(int(val_chan_id))
                        if val_chan:
                            view = ValidationButtons(self.bot, user.id,
                                                     name_msg.content,
                                                     prenom_msg.content)
                            await val_chan.send(embed=embed, view=view)

                except asyncio.TimeoutError:
                    try:
                        await user.send("⌛ Temps écoulé. Réagissez à nouveau pour recommencer.")
                    except:
                        pass
                except Exception as e:
                    await log_erreur(self.bot, channel.guild, f"check_reactions: {e}")
                    try:
                        await user.send("❌ Une erreur est survenue. Réessayez plus tard.")
                    except:
                        pass

        except Exception as e:
            # log erreur globale du polling
            await log_erreur(self.bot, None, f"check_reactions outer: {e}")

    # — Boucle de rappel (toutes les heures) —
    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            chan = self.bot.get_channel(int(cfg.get("salon_rappel_whitelist", 0)))
            if not chan:
                return
            for d in await self.charger_demandes():
                user = self.bot.get_user(int(d["user_id"]))
                if user:
                    nom = d.get("nom", "Inconnu")
                    prenom = d.get("prenom", "Inconnu")
                    await chan.send(f"⏰ Rappel : {user.mention} ({nom} {prenom}) en attente.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande: {e}")

    # — Commandes admin restantes —
    @app_commands.command(
        name="definir_journal_validation",
        description="Définit le salon de réception des demandes."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Journal défini sur {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_salon_rappel",
        description="Définit le salon pour rappels de demandes en attente."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["salon_rappel_whitelist"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de rappel défini sur {salon.mention}", ephemeral=True)

    @app_commands.command(
        name="definir_message_validation",
        description="Message DM envoyé lors de l'acceptation."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg["message_validation"] = message
        sauvegarder_config(cfg)
        await interaction.response.send_message("✅ Message de validation mis à jour.", ephemeral=True)

    @app_commands.command(
        name="rechercher_whitelist",
        description="Recherche un utilisateur dans la whitelist."
    )
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        from utils.utils import charger_whitelist
        approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        matches = [
            e for e in approved
            if query.lower() in e.get("nom", "").lower() or query.lower() in e.get("prenom", "").lower()
        ]
        if not matches:
            return await interaction.response.send_message(f"❌ Aucun résultat pour « {query} ».", ephemeral=True)
        texte = "\n".join(
            f"ID:{m['user_id']} • {m['nom']} {m['prenom']} (validé le {m['validated']})"
            for m in matches
        )
        embed = discord.Embed(title="Résultats", description=texte, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="retirer_whitelist",
        description="Retire un utilisateur de la whitelist et réinitialise son statut."
    )
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        from utils.utils import charger_whitelist, sauvegarder_whitelist
        approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
        found = next((e for e in approved if e["user_id"] == str(utilisateur.id)), None)
        if found:
            approved.remove(found)
            await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, approved)
        # rôles quoi qu'il arrive
        rm = discord.utils.get(interaction.guild.roles, name="Membre")
        rnv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
        if rm in utilisateur.roles:
            await utilisateur.remove_roles(rm)
        if rnv not in utilisateur.roles:
            await utilisateur.add_roles(rnv)
        msg = (
            f"✅ {utilisateur.mention} retiré de la whitelist et statut réinitialisé."
            if found else
            f"ℹ️ {utilisateur.mention} n'était pas en whitelist, statut réinitialisé."
        )
        await interaction.response.send_message(msg, ephemeral=True)

# — ValidationButtons inchangée pour le staff —
class ValidationButtons(discord.ui.View):
    def __init__(self, bot, user_id, nom, prenom):
        super().__init__(timeout=None)
        self.bot, self.user_id, self.nom, self.prenom = bot, user_id, nom, prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success, custom_id="valider_btn")
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if not user:
                return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
            # rôles
            nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            mb = discord.utils.get(interaction.guild.roles, name="Membre")
            if nv in user.roles:
                await user.remove_roles(nv)
            if mb not in user.roles:
                await user.add_roles(mb)
            # DM de bienvenue
            cfg = charger_config()
            try:
                await user.send(cfg.get("message_validation", "🎉 Bienvenue !"))
            except:
                pass
            # mise à jour whitelist
            from utils.utils import charger_whitelist, sauvegarder_whitelist
            wl = await interaction.client.loop.run_in_executor(None, charger_whitelist)
            if not any(e["user_id"] == str(user.id) for e in wl):
                wl.append({
                    "user_id": str(user.id),
                    "nom": self.nom,
                    "prenom": self.prenom,
                    "validated": datetime.utcnow().isoformat()
                })
                await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, wl)
            # cleanup
            await self.bot.get_cog("whitelist").supprimer_demande(user.id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("✅ Utilisateur accepté.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons accepter: {e}")
            try:
                await interaction.followup.send("❌ Erreur lors de la validation.", ephemeral=True)
            except:
                pass

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger, custom_id="refuser_btn")
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            user = interaction.guild.get_member(self.user_id)
            if user:
                try:
                    await user.send("❌ Votre demande a été refusée.")
                except:
                    pass
            await self.bot.get_cog("whitelist").supprimer_demande(self.user_id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons refuser: {e}")
            try:
                await interaction.followup.send("❌ Erreur lors du refus.", ephemeral=True)
            except:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
