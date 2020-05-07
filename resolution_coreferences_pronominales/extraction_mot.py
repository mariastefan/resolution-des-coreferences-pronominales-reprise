import re
import csv
from bs4 import BeautifulSoup
import requests
import os
import sys
import pickle


# Fonction permettant l'insertion du mot rq_word dans l'URL lors de la requete à jdm
# Appelée seulement dans extraction_html
def conversion_mot(rq_word: str):
    conversion_partielle = rq_word.encode('iso-8859-1')
    resultat = re.search("b[\"'](.*)[\"']$", str(conversion_partielle))
    resultat = resultat.group(1)
    resultat = resultat.replace("'", '%27')
    resultat = resultat.replace('\\x', '%')
    return resultat


# Prend rq_word (mot recherché) et retourne le code html correspondant depuis http://www.jeuxdemots.org/rezo-dump
def extraction_html(rq_word: str, type_relation: str):
    rq_word_converti = conversion_mot(rq_word)
    if type_relation == 'all':
        html = requests.get(
            'http://www.jeuxdemots.org/rezo-dump.php?gotermsubmit=Chercher&gotermrel=' + rq_word_converti + '&rel=')
    else:
        html = requests.get(
            'http://www.jeuxdemots.org/rezo-dump.php?gotermsubmit=Chercher&gotermrel=' + rq_word_converti + '&rel=' +
            type_relation)
    encoding = html.encoding if "charset" in html.headers.get("content-type", "").lower() else None
    soup = BeautifulSoup(html.content, 'html.parser', from_encoding='iso-8859-1')
    texte_brut = soup.find_all('code')
    return texte_brut


# Prend le mot ainsi que le type de la relation (pour toutes les relations alors type_relation = 'all').
# Retourne un tableau DataFrame avec les colonnes 'id_relation', 'lautre_noeud', 'type_relation',
# 'poids_relation', 'sens_relation'
# Ce tableau contient les relations sortantes et entrantes du mot, récupérées depuis jdm.
def relations_mot(mot: str, type_relation: str, cache: int):
    def sans_cache(mot_tmp, type_relation_tmp):
        texte_brut = extraction_html(mot_tmp, type_relation_tmp)
        try:
            lignes_noeuds_et_relations = re.findall("[re];[0-9]*;.*", str(texte_brut))
            if not lignes_noeuds_et_relations:
                raise ValueError("Le mot " + mot_tmp + " n'existe pas sur jeuxdemots.org !")
        except ValueError as err:
            print("ValueError : "+str(err))
            sys.exit()
        tab_eids = {}
        tab_rids = {}
        eid_mot = re.search("e;([0-9]*);.*", lignes_noeuds_et_relations[0]).group(1)
        stop = 0
        for a in lignes_noeuds_et_relations:
            if stop == 0:
                result_noeud = re.search("e;([0-9]*);'(.*)';([0-9]*);(-*[0-9]*);*'*([^']*)'*", str(a))
                if result_noeud:
                    if len(tab_eids) != 0 and result_noeud.group(1) in tab_eids.keys():
                        raise KeyError("Probleme dans jdm : eid doit etre unique")
                    poids = result_noeud.group(4)
                    if not poids or poids == '':
                        poids = '0'
                    tab_eids[result_noeud.group(1)] = [result_noeud.group(2),
                                                       result_noeud.group(3),
                                                       poids,
                                                       result_noeud.group(5)]
            result_rel = re.search("r;([0-9]*);([0-9]*);([0-9]*);([0-9]*);(-*[0-9]*)", str(a))
            if result_rel:
                stop = 1
                poids = result_rel.group(5)
                if not poids or poids == '':
                    poids = '0'
                if len(tab_rids) != 0 and result_rel.group(1) in tab_rids.keys():
                    del tab_rids[result_rel.group(1)]
                    tab_rids[result_rel.group(1) + '_entrante'] = [result_rel.group(2),
                                                                   result_rel.group(3),
                                                                   result_rel.group(4),
                                                                   poids,
                                                                   'entrante+sortante']
                    tab_rids[result_rel.group(1) + '_sortante'] = [result_rel.group(2),
                                                                   result_rel.group(3),
                                                                   result_rel.group(4),
                                                                   poids,
                                                                   'entrante+sortante']
                else:
                    tab_rids[result_rel.group(1)] = [result_rel.group(2),
                                                     result_rel.group(3),
                                                     result_rel.group(4),
                                                     poids]
                    if result_rel.group(1) not in tab_rids.keys():
                        raise KeyError(
                            "Creation tab_rids : la cref " + str(result_rel.group(1)) + " n'a pas pu etre cree")
        max_positif = 0
        min_negatif = 0
        for i in range(len(list(tab_rids.values()))):
            poids = int(list(tab_rids.values())[i][3])
            if poids >= 0 and poids > max_positif:
                max_positif = poids
            if poids < 0 and poids < min_negatif:
                min_negatif = poids

        relations_dico = {}

        for rid in list(tab_rids.keys()):
            poids = int(tab_rids[rid][3])
            if poids < 0:
                poids = (poids / min_negatif) * (-1)
            else:
                poids = poids / max_positif

            if len(tab_rids[rid]) == 5 and tab_rids[rid][0] == tab_rids[rid][1]:
                res = re.search(r'.*(sortante|entrante)', rid)
                relations_dico[rid] = [tab_eids[tab_rids[rid][0]][0],
                                       tab_rids[rid][2],
                                       poids,
                                       res.group(1)]
            elif tab_rids[rid][0] == eid_mot:
                relations_dico[rid] = [tab_eids[tab_rids[rid][1]][0],
                                       tab_rids[rid][2],
                                       poids,
                                       'sortante']
            elif tab_rids[rid][1] == eid_mot:
                relations_dico[rid] = [tab_eids[tab_rids[rid][0]][0],
                                       tab_rids[rid][2],
                                       poids,
                                       'entrante']

        if not os.path.isdir('./cache'):
            try:
                os.mkdir("./cache")
            except OSError:
                print("Creation of the directory cache failed")
        fichier_cache = open('./cache/' + mot_tmp + '_' + type_relation_tmp + '.pkl', "wb")
        pickle.dump(relations_dico, fichier_cache)
        fichier_cache.close()
        return relations_dico

    if cache == 0:
        return sans_cache(mot, type_relation)
    elif cache == 1 and (
            not os.path.isdir('./cache') or not os.path.isfile('./cache/' + mot + '_' + type_relation + '.pkl')):
        return sans_cache(mot, type_relation)
    elif cache == 1:
        fichier = open('./cache/' + mot + '_' + type_relation + '.pkl', "rb")
        relations = pickle.load(fichier)
        fichier.close()
        return relations
    else:
        sys.exit("cache doit etre egal a 0 ou 1")
