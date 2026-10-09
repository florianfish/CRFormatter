"""Parcours de la secrétaire dans un vrai navigateur (Playwright + Google Chrome).

À lancer sur une instance de développement : `make e2e`.
Usage : parcours_secretaire.py URL EXEMPLE.html DOSSIER_CAPTURES
(EXEMPLE.html : le compte rendu tel que Word le place dans le presse-papiers, cf. scripts/exemple.py)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

URL, EXEMPLE, SP = sys.argv[1], Path(sys.argv[2]).read_text(encoding="utf-8"), sys.argv[3]
erreurs = []


def coller(page, html):
    """Colle un compte rendu dans le cadre de la page d'accueil, comme un Ctrl+V depuis Word."""
    page.goto(URL)
    page.locator("#zone-collage").evaluate("""(zone, html) => {
        const donnees = new DataTransfer();
        donnees.setData("text/html", html);
        donnees.setData("text/plain", "texte");
        zone.dispatchEvent(new ClipboardEvent("paste", { clipboardData: donnees, bubbles: true, cancelable: true }));
    }""", html)
    page.wait_for_url("**/lot/**")

with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome", args=["--no-sandbox"])
    page = nav.new_page(viewport={"width": 1100, "height": 900})
    page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("console", lambda m: m.type == "error" and erreurs.append(m.text))

    # 1. Collage du compte rendu
    coller(page, EXEMPLE)
    expect(page.locator(".verification")).to_contain_text("dispnée")
    expect(page.locator("#notification")).to_be_hidden()
    print("1. compte rendu collé et formaté, mots à vérifier affichés")

    # 2. Taper un remplacement coche « Remplacer par » ; « Créat » est déclaré correct
    mot = page.locator("fieldset.mot", has_text="dispnée")
    mot.locator("input[type=text]").fill("dyspnée")
    assert mot.locator("input[value=remplacer]").is_checked()
    page.locator("fieldset.mot", has_text="Créat").get_by_label("Le mot est correct").check()
    page.click("text=Enregistrer mes choix et reformater")
    expect(page.locator(".message.succes")).to_contain_text("C'est noté")
    expect(page.locator(".verification")).to_have_count(0)
    expect(page.locator(".apercu")).to_contain_text("dyspnée")
    page.screenshot(path=f"{SP}/apres-choix.png", full_page=True)
    print("2. choix enregistrés, document reformaté sans mot à vérifier")

    # 3. Bouton « Annuler » du message : les mots reviennent
    page.click("#annuler-decisions")
    page.wait_for_load_state("networkidle")
    expect(page.locator(".verification")).to_contain_text("dispnée")
    print("3. annulation depuis le résultat : mots à vérifier de retour")

    # 4. Vocabulaire : ajout d'un remplacement puis annulation via la notification
    page.goto(URL + "vocabulaire")
    # Noms de médicaments proposés pendant la frappe dans « écrire »
    page.fill("#form-remplacement [name=par]", "dolip")
    expect(page.locator("#form-remplacement datalist option[value=Doliprane]")).to_have_count(1)
    page.fill("#form-remplacement [name=texte]", "ttt")
    page.fill("#form-remplacement [name=par]", "traitement")
    page.click("#form-remplacement button")
    expect(page.locator("#liste-remplacements")).to_contain_text("traitement")
    expect(page.locator("#notification")).to_contain_text("Remplacement ajouté")
    page.screenshot(path=f"{SP}/notification.png")
    page.click("#notification button")
    page.wait_for_load_state("networkidle")
    expect(page.locator("#liste-remplacements")).not_to_contain_text("ttt")
    print("4. remplacement ajouté puis annulé depuis la notification")

    # 5. Erreur compréhensible
    page.fill("#form-mot [name=mot]", "deux mots")
    page.click("#form-mot button")
    expect(page.locator("#notification")).to_contain_text("Un seul mot")
    print("5. message d'erreur clair")

    # 6. Rubrique : ajout d'une écriture reconnue
    rubrique = page.locator(".rubrique", has_text="Antécédents chirurgicaux")
    rubrique.locator("input").fill("atcd chirurgie")
    rubrique.locator("button[type=submit]").click()
    expect(page.locator(".rubrique", has_text="Antécédents chirurgicaux")).to_contain_text("atcd chirurgie")
    print("6. écriture de rubrique ajoutée")

    # 7. Mise en forme : interrupteur
    page.goto(URL + "mise-en-forme")
    page.locator(".interrupteur", has_text="Guillemets français").click()
    expect(page.locator("#notification")).to_contain_text("désactivé")
    page.reload()
    assert not page.locator(".interrupteur", has_text="Guillemets français").locator("input").is_checked()
    print("7. interrupteur désactivé et conservé après rechargement")

    # 8. Historique : retour à la version initiale
    page.goto(URL + "historique")
    page.screenshot(path=f"{SP}/historique.png", full_page=True)
    page.on("dialog", lambda d: d.accept())
    page.locator(".historique li").last.locator("button").click()
    page.wait_for_load_state("networkidle")
    expect(page.locator(".historique li").first).to_contain_text("Retour à la version du")
    page.goto(URL + "mise-en-forme")
    assert page.locator(".interrupteur", has_text="Guillemets français").locator("input").is_checked()
    print("8. retour à l'état initial depuis l'historique")

    # 9. Mode expert accessible
    assert page.goto(URL + "expert").status == 200
    expect(page.locator("#liste-regles .regle").first).to_be_visible()
    print("9. mode expert accessible")

    # 10. Retouche manuelle du compte rendu
    coller(page, EXEMPLE)
    page.click("text=Retoucher")
    page.wait_for_selector("#feuille .bloc")
    expect(page.locator("#feuille mark.inconnu").first).to_be_visible()

    # Modifier un paragraphe : curseur à la fin, saisie, puis Entrée pour en créer un nouveau
    paragraphe = page.locator("#feuille p.bloc", has_text="douleur thoracique")
    paragraphe.click()
    page.keyboard.press("End")
    page.keyboard.type(" (retouche)")
    page.keyboard.press("Enter")
    page.keyboard.type("Nouveau paragraphe saisi")
    expect(page.locator("#etat")).to_have_text("Modifications non enregistrées")

    # Annuler : la frappe puis la création du paragraphe
    page.click('[data-action="annuler"]')
    page.click('[data-action="annuler"]')
    expect(page.locator("#feuille p.bloc", has_text="Nouveau paragraphe saisi")).to_have_count(0)
    paragraphe.click()
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    page.keyboard.type("Nouveau paragraphe saisi")

    # Retour arrière en début de paragraphe : fusion avec le précédent
    page.locator("#feuille p.bloc", has_text="Nouveau paragraphe saisi").click()
    page.keyboard.press("Home")
    page.keyboard.press("Backspace")
    expect(page.locator("#feuille p.bloc", has_text="(retouche)Nouveau paragraphe saisi")).to_be_visible()

    # Remplacer un mot inconnu dans ce document depuis le panneau
    mot = page.locator(".liste-mots li", has_text="dispnée")
    mot.locator("input[type=text]").fill("dyspnée")
    mot.get_by_role("button", name="Remplacer").click()
    expect(page.locator("#feuille")).to_contain_text("dyspnée d'effort")

    # Gras avec le bouton, italique avec Ctrl+I, sur le dernier mot sélectionné au clavier
    examen = page.locator("#feuille p.bloc", has_text="Patient eupnéique")
    examen.click()
    page.keyboard.press("Control+Home")
    page.keyboard.press("End")
    page.keyboard.press("Shift+Control+ArrowLeft")
    page.keyboard.press("Shift+Control+ArrowLeft")  # « apyrétique. » : le mot et le point
    page.click('[data-action="gras"]')
    expect(page.locator('[data-action="gras"]')).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Control+i")
    page.locator("#feuille p.bloc", has_text="Motif").click()  # quitter le paragraphe
    expect(page.locator("#feuille p.bloc", has_text="Patient eupnéique").locator("b i, i b")).to_have_count(1)

    # Cellule de tableau
    page.locator("#feuille td p", has_text="Troponine").click()
    page.keyboard.press("End")
    page.keyboard.type(" Tn")

    page.click("#enregistrer")
    expect(page.locator("#etat")).to_have_text("Enregistré")
    page.screenshot(path=f"{SP}/retouche.png", full_page=True)
    with page.expect_download() as telechargement:
        page.click("#telecharger")
    from docx import Document
    doc = Document(telechargement.value.path())
    textes = [p.text for p in doc.paragraphs]
    assert any("(retouche)Nouveau paragraphe saisi" in t for t in textes), textes
    assert any("dyspnée d'effort" in t for t in textes), textes
    assert doc.tables[0].cell(0, 0).text == "Troponine Tn"
    examen_docx = next(p for p in doc.paragraphs if p.text.startswith("Patient eupnéique"))
    styles = [(r.text, bool(r.bold), bool(r.italic)) for r in examen_docx.runs if r.text]
    assert styles[0] == ("Patient eupnéique, ", False, False) and styles[1][1:] == (True, True), styles
    assert any(p.text.endswith("Docteur Martin") and p.text.startswith("\t" * 6) for p in doc.paragraphs)
    print("10. retouche : saisie, paragraphes, annulation, fusion, remplacement, gras/italique, tableau, .docx")

    page.click("text=← Retour au résultat")
    expect(page.locator(".pastille", has_text="retouché à la main")).to_be_visible()
    print("11. document marqué « retouché à la main » dans le résultat")

    # 12. Collage depuis Word puis « Copier pour Word » (HTML du presse-papiers tel que Word le produit)
    html_word = """<html xmlns:o="urn:schemas-microsoft-com:office:office"><head><style>
    p.MsoNormal {margin:0cm; margin-bottom:8.0pt; line-height:107%; font-size:11.0pt; font-family:"Arial",sans-serif;}
    p.MsoListParagraph {margin-left:36.0pt; text-indent:-18.0pt; margin-bottom:0cm; font-size:11.0pt; font-family:"Arial",sans-serif;}
    </style></head><body lang=FR><div class=WordSection1>
    <p class=MsoNormal align=center style='text-align:center'><b><u><span style='font-size:12.0pt'>COMPTE-RENDU
    DE CONSULTATION</span></u></b></p>
    <p class=MsoNormal><o:p>&nbsp;</o:p></p>
    <p class=MsoNormal><b><u>ATCD</u></b> : HTA , diabéte<span style='mso-tab-count:1'>   </span>type 2</p>
    <p class=MsoListParagraph><![if !supportLists]><span style='font-family:Symbol;mso-list:Ignore'>·<span
    style='font:7.0pt "Times New Roman"'>&nbsp;&nbsp; </span></span><![endif]>suivi pulmonaire</p>
    <table class=MsoTableGrid border=1 cellspacing=0 cellpadding=0 style='border-collapse:collapse;border:none'>
    <tr><td style='border:solid windowtext 1.0pt'><p class=MsoNormal>Créatinine</p></td>
    <td style='border:solid windowtext 1.0pt'><p class=MsoNormal>96µmol/L</p></td></tr></table>
    <p class=MsoNormal>Poids : 72kg<br>Taille : 1m80</p>
    <p class=MsoNormal><b><u>Biologie</u></b> :</p>
    <p class=MsoNormal>Hb (g/dL) : 13,4</p><p class=MsoNormal>Plaquettes (Giga/L) : 294</p>
    <p class=MsoNormal><o:p>&nbsp;</o:p></p>
    <p class=MsoNormal>CRP (mg/L) : &lt;1.0</p><p class=MsoNormal>Na (mmol/L) : 144</p>
    </div></body></html>"""
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    coller(page, html_word)
    # Récapitulatif des corrections avant toute retouche
    expect(page.locator("h2", has_text="Compte rendu collé")).to_be_visible()
    expect(page.locator(".changements")).to_be_visible()
    expect(page.locator(".changements")).to_contain_text("diabète")
    expect(page.locator(".changements")).to_contain_text("4 résultats sur 2 colonnes")
    page.screenshot(path=f"{SP}/collage-resultat.png", full_page=True)
    page.click("button.copier")
    expect(page.locator("#notification")).to_contain_text("Copié")
    html_resultat = page.evaluate("""async () => {
        const [element] = await navigator.clipboard.read();
        return await (await element.getType("text/html")).text();
    }""")
    assert "<b><u>COMPTE-RENDU DE CONSULTATION</u></b>" in html_resultat, html_resultat
    page.click("text=Retoucher")
    page.wait_for_url("**/document/0")
    expect(page.locator("h1")).to_have_text("Relire le compte rendu")
    blocs = page.locator("#feuille > p.bloc")
    expect(blocs.nth(0)).to_have_text("COMPTE-RENDU DE CONSULTATION")
    expect(blocs.nth(0)).to_have_css("text-align", "center")
    expect(blocs.nth(0).locator("b u, u b")).to_have_count(1)
    expect(blocs.nth(1)).to_have_text("")
    expect(blocs.nth(2)).to_have_text("Antécédents\u00a0: HTA, diabète\ttype 2")
    expect(blocs.nth(3)).to_have_text("-\tSuivi pulmonaire")
    expect(blocs.nth(3)).to_have_css("margin-left", "48px")  # 36 pt
    expect(page.locator("#feuille td p").nth(1)).to_have_text("96\u00a0µmol/L")
    expect(blocs.nth(4)).to_contain_text("72\u00a0kg")
    # Résultats d'analyse sur deux colonnes, coupées sur la ligne vide entre les deux groupes
    colonnes = page.locator("#feuille table.bloc-tableau").nth(1).locator("td")
    expect(colonnes).to_have_count(2)
    expect(colonnes.nth(0)).to_contain_text("Plaquettes")
    expect(colonnes.nth(1)).to_contain_text("CRP")
    page.screenshot(path=f"{SP}/collage.png", full_page=True)

    page.click("#copier")
    expect(page.locator("#notification")).to_contain_text("Copié")
    copie = page.evaluate("""async () => {
        const [element] = await navigator.clipboard.read();
        return { html: await (await element.getType("text/html")).text(),
                 texte: await (await element.getType("text/plain")).text() };
    }""")
    html = copie["html"]
    assert "text-align: center" in html and "<b><u>COMPTE-RENDU DE CONSULTATION</u></b>" in html, html
    assert 'font-family: Arial' in html or 'font-family: "Arial"' in html, html
    assert "font-size: 12pt" in html and "font-size: 11pt" in html, html
    assert "margin-bottom: 8pt" in html and "line-height: 107%" in html, html
    assert 'mso-tab-count:1' in html and "margin-left: 36pt" in html and "text-indent: -18pt" in html, html
    assert "border:solid windowtext 1pt" in html and "Créatinine" in html, html
    assert "width:100%" in html and "width:50.00%" in html, html  # colonnes de résultats
    assert "72\u00a0kg<br>Taille" in html or "72&nbsp;kg<br>Taille" in html, html
    assert copie["texte"].startswith("COMPTE-RENDU DE CONSULTATION\r\n\r\nAntécédents"), copie["texte"]

    # Lignes vides dans une colonne de résultats : créées avec Entrée, retirées avec Retour arrière et Suppr
    colonne = page.locator("#feuille table.bloc-tableau").nth(1).locator("td").nth(0)
    expect(colonne.locator("p.bloc")).to_have_count(2)
    colonne.locator("p.bloc").nth(0).click()
    page.keyboard.press("End")
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    expect(colonne.locator("p.bloc")).to_have_count(4)
    page.keyboard.press("Backspace")
    expect(colonne.locator("p.bloc")).to_have_count(3)
    colonne.locator("p.bloc").nth(0).click()
    page.keyboard.press("End")
    page.keyboard.press("Delete")
    expect(colonne.locator("p.bloc")).to_have_count(2)
    expect(colonne.locator("p.bloc").nth(1)).to_contain_text("Plaquettes")
    # Suppr en fin de ligne dans le corps : la ligne vide sous le titre disparaît
    page.locator("#feuille > p.bloc").nth(0).click()
    page.keyboard.press("End")
    page.keyboard.press("Delete")
    expect(page.locator("#feuille > p.bloc").nth(1)).to_contain_text("Antécédents")
    page.click("#enregistrer")
    expect(page.locator("#etat")).to_have_text("Enregistré")
    print("12. collage depuis Word : récapitulatif, copie depuis le résultat et l'éditeur, mise en page reprise")

    nav.close()

# 422 (saisie refusée, étape 5) est attendu.
inattendues = [e for e in erreurs if "status of 422" not in e]
print("Erreurs JavaScript inattendues :", inattendues or "aucune")
sys.exit(1 if inattendues else 0)
