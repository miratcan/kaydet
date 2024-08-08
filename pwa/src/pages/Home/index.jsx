/*
Tags:

Type - Log, Note, Decision, MileStone
Mood - Great, Good, Ok, Bad, Miserable
Activity - User Defined

*/
import { Entry } from "../../components/Entry";
import { useState, useEffect } from "preact/hooks";

const types = {
  "note": "Note",
  "log": "Log",
  "milestone": "Mile Stone",
  "decision": "Decision"
}
const activities = {
  "family": { "emoji": "", "text": "Family"}
}
const tags = {
  "mood": { "type": "numberic"},
  "activity": { "type": "select", "choices": activities}
}

function Select({ options, callback }) {

  const [selected, setSelected] = useState(null);
  useEffect(() => { if ( callback ) { callback(selected) } }, [selected]);

  return (
    <select onchange={(e) => setSelected(e.target.value)}>
      {Object.entries(options).map(([key, val]) => {
        return (<option value={ key }>{ val }</option>)
      })}
    </select>
  )
}

function EntryTypeSelect() {
  return (
    <Select options={types} />
  )
}

function ActivitySelect() {
  return (
    <select>
      {
        Object.entries(activities).map(([key, val]) => {
          return (
            <option value={ key }>{ val }</option>
          )
        })
      }
    </select>
  )
}

function Form() {
  return (
    <div class="form-wrapper">
      <form>
        <EntryTypeSelect />

          <input type="range" min="1" max="100" value="50" class="slider" id="myRange" />
        <textarea></textarea>
        <div class="row">
          <button>Reset</button>
          <input type="submit" />
        </div>
          
      </form>
    </div>
  )
}

function Footer() {
  const [isOpen, setIsOpen]= useState(false);
  const toggle = () => {
    setIsOpen((state) => !state )
  }
  return (
    <footer class={ isOpen ? 'open' : 'closed' }>
      <button id="footer-switch" onclick={ toggle }>
        { isOpen ? 'Close' : 'Open' }
      </button>
      <Form />
    </footer>
  )
}

export function Home() {
  const data = [
    {
      "type": "note",
      "title": "This is the title",
      "tags": {
        "mood": 3,
        "activity": "family"
      },
      "content": ["Pig sausage cow porchetta strip andouille chuck pastrami fatback ball. Tenderloin alcatra pig ground boudin sausage capicola bone brisket pastrami kielbasa. Shankle tail tri round pork brisket shankle alcatra pork steak. Ground pig ham ribs tri salami spare rump doner. Steak brisket alcatra jerky andouille pork meatball brisket turkey chuck."],
      "tstamp": "12:12:2024",
    }, {
      "type": "decision",
      "title": "Lololo",
      "tags": {
        "mood": 3,
        "activity": "family"
      },
      "content": [
        "Brisket hock kielbasa doner shoulder bresaola shoulder spare. Ball hock ball meatball meatloaf boudin chuck ribs jowl meatball. Biltong round tenderloin sirloin shoulder t steak turkey sirloin ribeye short shank sausage flank prosciutto. Tongue burgdoggen boudin kielbasa loin tenderloin porchetta venison corned hamburger shoulder venison. Short fatback bresaola hock spare filet landjaeger tongue jowl pastrami.",
        "Bresaola fatback pastrami picanha tail hamburger burgdoggen porchetta. Boudin flank prosciutto ribeye kevin tri bone cupim shankle meatloaf tenderloin strip swine frankfurter. Prosciutto chop belly tip tenderloin beef cupim salami biltong tip leberkas tri shoulder meatloaf. Doner ground pancetta bacon turkey ribeye brisket sirloin tongue burgdoggen porchetta cupim corned. Leberkas swine ribeye boudin strip kielbasa leberkas spare meatball sausage andouille burgdoggen tip ribeye rump.",
        "Doner andouille hamburger bacon pancetta strip bacon fatback doner filet beef sirloin chicken pancetta. Burgdoggen pastrami sirloin turkey fatback tail pancetta chop. Hock fatback rump shank brisket cupim shank hamburger sausage. Pastrami flank salami ground drumstick chuck sausage tail shankle tenderloin ground. Bacon chuck pig pastrami tenderloin buffalo chuck porchetta sirloin."
      ]
    }
  ]
	return (
    <>
    <main>
      <div class="date">
        <h2>24/08/2024</h2>
        {data.map((entry) => {
          return <Entry data={entry} />
        })}
      </div>
    </main>
    <Footer />
    </>
  )
}

