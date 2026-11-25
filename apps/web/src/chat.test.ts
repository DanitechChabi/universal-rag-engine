import { describe, expect, it } from "vitest";
import { parseSse, splitCitations } from "./chat";

describe("flux de réponse", () => {
  it("découpe les évènements, même coupés en plusieurs paquets", () => {
    const first = parseSse('event: meta\ndata: {"message_id":"m","conversation_id":"c","model":null}\n\nevent: token\ndata: {"te');
    expect(first.events).toHaveLength(1);
    expect(first.events[0].name).toBe("meta");
    const second = parseSse(first.rest + 'xt":"Le loyer"}\n\n');
    expect(second.events).toEqual([{ name: "token", data: { text: "Le loyer" } }]);
    expect(second.rest).toBe("");
  });

  it("isole les références sans interpréter de HTML", () => {
    expect(splitCitations("Loyer de 450 000 FCFA [1] et durée de 3 ans [2].")).toEqual([
      "Loyer de 450 000 FCFA ",
      1,
      " et durée de 3 ans ",
      2,
      ".",
    ]);
    // Un balisage éventuel reste du texte : React l'échappe à l'affichage.
    expect(splitCitations("<img src=x onerror=alert(1)> [1]")).toEqual(["<img src=x onerror=alert(1)> ", 1]);
  });
});
