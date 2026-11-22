/**
 * Wesley mobile ne s'affiche que sur un téléphone. Le serveur refuse déjà les navigateurs d'ordinateur
 * (serveur/app.py, est_telephone) ; cette vérification côté page couvre le reste (copie en cache, page
 * enregistrée, User-Agent modifié) : il faut un écran tactile, un pointeur « grossier » (doigt) et un petit écran.
 * Sur ordinateur, l'appli de bureau Wesley fait tout cela (et bien plus).
 */
export function estTelephone(): boolean {
  const ua = navigator.userAgent;
  const uaTel = /iPhone|iPod|Android.+Mobile|Mobile.+Android|Windows Phone|IEMobile|Opera Mini|Mobile Safari/i.test(ua);
  const indice = (navigator as any).userAgentData?.mobile as boolean | undefined;
  const tactile = navigator.maxTouchPoints > 0 && matchMedia("(pointer: coarse)").matches;
  const sansSouris = !matchMedia("(any-pointer: fine)").matches || matchMedia("(hover: none)").matches;
  const petit = Math.min(screen.width, screen.height) <= 600;
  if (indice === false && !/iPhone|iPod/.test(ua)) return false;
  return (uaTel || indice === true) && tactile && sansSouris && petit;
}
